#!/usr/bin/env python3
"""Build AVIF, WebP and resized JPEG variants from the photos already on each page.

Original JPG/PNG files stay in place. Metadata is stripped without recompressing
pixels (exiftool -all=). Variants are only scaled down, never cropped or upscaled,
and each one is encoded from that same source file. The img src in every
<picture> remains the original, so the fallback stays the locked photo.

Page markup for grids and product galleries is also emitted by assets/js/site.js
from /assets/img-variants.json. scripts/build-pages.py is what the site comments
refer to, but it is not in this repository, so the static HTML and site.js are
both updated here.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HASH_BEFORE = Path("/tmp/pixel-hashes-before.txt")
REPORT_PATH = Path("/tmp/optim-report.json")
MANIFEST_PATH = ROOT / "assets" / "img-variants.json"

STANDARD_WIDTHS = (400, 800, 1200, 1600)
# Homepage heroes are about 447 device px on the Lighthouse mobile preset.
# 600px is used when that file is smaller than the 800px AVIF. AKARI 55D's
# 600px AVIF is larger than its 800px file, so it gets 480px instead (still
# above the slot, still smaller than 800px, SSIM >= 0.98).
EXTRA_WIDTHS = {
    "assets/products/akari-55d/1.jpg": (480,),
    "assets/products/heller-swell-white/1.jpg": (600,),
    "assets/products/akari-45d/1.jpg": (600,),
    "assets/products/dulton-double-face-clock-green/1.jpg": (600,),
}
SSIM_MIN = 0.98
AVIF_LADDER = (55, 60, 65, 70, 75, 80, 85, 90, 95)
WEBP_LADDER = (80, 85, 90, 95, 100)
JPG_LADDER = (85, 90, 93, 96, 98)
HERO_BYTES = 150 * 1024
CARD_BYTES = 60 * 1024
# Lighthouse mobile: 412 CSS px, deviceScaleFactor 1.75 (Moto G Power preset).
MOBILE_CSS = 412
MOBILE_DPR = 1.75

CARD_SIZES = "(min-width: 1100px) 300px, (min-width: 760px) 31vw, 48vw"
GALLERY_SIZES = "(min-width: 900px) 52vw, 100vw"
HERO_SIZES = "(min-width: 900px) 30vw, 62vw"
IG_SIZES = "(min-width: 800px) 16vw, 33vw"
THUMB_SIZES = "76px"

IMG_TAG = re.compile(r"<img\b[^>]*>", re.I)
ATTR = re.compile(
    r"""([^\s=/"']+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+)))?"""
)


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def ssim(candidate: Path, reference: Path, work: Path) -> float:
    decoded = work / "decoded.png"
    if candidate.suffix.lower() == ".png":
        decoded = candidate
    else:
        run(["convert", str(candidate), f"png24:{decoded}"])
    proc = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-i", str(decoded), "-i", str(reference),
            "-lavfi", "ssim", "-f", "null", "-",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    match = re.search(r"All:([0-9.]+)", proc.stderr)
    if not match:
        raise RuntimeError(f"SSIM failed for {candidate}: {proc.stderr[-400:]}")
    return float(match.group(1))


def widths_for(intrinsic: int, rel: str = "") -> list[int]:
    chosen = [w for w in STANDARD_WIDTHS if w < intrinsic]
    for width in EXTRA_WIDTHS.get(rel, ()):
        if width < intrinsic and width not in chosen:
            chosen.append(width)
    if intrinsic not in chosen:
        chosen.append(intrinsic)
    return sorted(chosen)


def make_ref(src: Path, width: int, intrinsic: int, dest: Path) -> tuple[int, int]:
    cmd = ["convert", str(src), "-strip"]
    if width < intrinsic:
        cmd += ["-filter", "Lanczos", "-resize", f"{width}x"]
    cmd.append(f"png24:{dest}")
    run(cmd)
    proc = subprocess.run(
        ["identify", "-format", "%w %h", str(dest)],
        check=True, capture_output=True, text=True,
    )
    w, h = (int(n) for n in proc.stdout.split())
    if w != width:
        raise RuntimeError(f"{src} resized to {w}px, wanted {width}")
    return w, h


def encode_avif(ref: Path, dest: Path, quality: int, yuv: str) -> None:
    cmd = [
        "avifenc", "-q", str(quality), "-s", "6", "-j", "1",
        "--ignore-exif", "--ignore-xmp", "--ignore-icc", "-y", yuv,
    ]
    if yuv == "420":
        cmd.append("--sharpyuv")
    cmd += [str(ref), str(dest)]
    run(cmd)


def encode_webp(ref: Path, dest: Path, quality: int) -> None:
    run(["cwebp", "-q", str(quality), "-m", "4", "-metadata", "none", str(ref), "-o", str(dest)])


def encode_jpg(ref: Path, dest: Path, quality: int) -> None:
    # 4:4:4 keeps chroma. 4:2:0 can sit under SSIM 0.98 even at quality 98.
    run([
        "convert", str(ref), "-quality", str(quality),
        "-sampling-factor", "4:4:4", "-strip", str(dest),
    ])


def search_quality(ladder: tuple[int, ...], encode) -> tuple[int, float, bool]:
    """Lowest ladder step whose SSIM clears the floor. encode(q) -> ssim."""
    best_q = None
    best_ssim = -1.0
    lo, hi = 0, len(ladder) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        score = encode(ladder[mid])
        if score >= SSIM_MIN:
            best_q, best_ssim = ladder[mid], score
            hi = mid - 1
        else:
            lo = mid + 1
    if best_q is None:
        score = encode(ladder[-1])
        return ladder[-1], score, False
    return best_q, best_ssim, True


def process_source(src_str: str) -> dict:
    src = Path(src_str)
    ident = subprocess.run(
        ["identify", "-format", "%w %h %[opaque]", str(src)],
        check=True, capture_output=True, text=True,
    )
    intrinsic_s, height_s, opaque = ident.stdout.split()
    intrinsic, intrinsic_h = int(intrinsic_s), int(height_s)
    opaque = opaque.strip() == "true" or opaque.strip() == "True"
    rel = src.relative_to(ROOT).as_posix()
    widths = widths_for(intrinsic, rel)
    url = "/" + rel
    variants = []
    min_ssim = 1.0
    with tempfile.TemporaryDirectory(prefix="ttimg-") as tmp:
        work = Path(tmp)
        ref = work / "ref.png"
        trial = work / "trial"
        win = work / "win"
        for width in widths:
            ref_w, ref_h = make_ref(src, width, intrinsic, ref)
            expect_h = intrinsic_h if width == intrinsic else max(1, round(intrinsic_h * width / intrinsic))
            if abs(ref_h - expect_h) > 2:
                raise RuntimeError(f"{src} {width}px height {ref_h} != {expect_h} (crop or stretch)")

            def encode_try(kind: str, quality: int, yuv: str = "420") -> float:
                if kind == "avif":
                    encode_avif(ref, trial.with_suffix(".avif"), quality, yuv)
                    path = trial.with_suffix(".avif")
                elif kind == "webp":
                    encode_webp(ref, trial.with_suffix(".webp"), quality)
                    path = trial.with_suffix(".webp")
                else:
                    encode_jpg(ref, trial.with_suffix(".jpg"), quality)
                    path = trial.with_suffix(".jpg")
                score = ssim(path, ref, work)
                if score >= SSIM_MIN:
                    shutil.copy(path, win.with_suffix(path.suffix))
                return score

            q, score, ok = search_quality(AVIF_LADDER, lambda q: encode_try("avif", q, "420"))
            yuv = "420"
            if not ok:
                q, score, ok = search_quality(AVIF_LADDER, lambda q: encode_try("avif", q, "444"))
                yuv = "444"
            if not ok:
                # Keep the best 4:4:4 attempt already copied only on pass.
                # Re-encode the top 4:4:4 step so a file exists either way.
                encode_try("avif", AVIF_LADDER[-1], "444")
                if not win.with_suffix(".avif").exists():
                    shutil.copy(trial.with_suffix(".avif"), win.with_suffix(".avif"))
                    score = ssim(win.with_suffix(".avif"), ref, work)
            avif_out = src.parent / "r" / f"{src.stem}-{width}.avif"
            avif_out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(win.with_suffix(".avif"), avif_out)
            avif_ssim = ssim(avif_out, ref, work)
            min_ssim = min(min_ssim, avif_ssim)
            variants.append({
                "fmt": "avif", "w": width, "h": ref_h, "q": q, "yuv": yuv,
                "ssim": avif_ssim, "bytes": avif_out.stat().st_size,
                "ok": avif_ssim >= SSIM_MIN, "url": "/" + avif_out.relative_to(ROOT).as_posix(),
            })
            win.with_suffix(".avif").unlink(missing_ok=True)

            q, score, ok = search_quality(WEBP_LADDER, lambda q: encode_try("webp", q))
            if not ok:
                # Lossy WebP is 4:2:0. A few detailed frames stay under 0.98 even at q=100,
                # so those fall back to a lossless WebP (SSIM 1 against the same-size original).
                run(["cwebp", "-lossless", "-metadata", "none", str(ref), "-o", str(win.with_suffix(".webp"))])
                q = 100
            webp_out = src.parent / "r" / f"{src.stem}-{width}.webp"
            shutil.copy(win.with_suffix(".webp"), webp_out)
            webp_ssim = ssim(webp_out, ref, work)
            min_ssim = min(min_ssim, webp_ssim)
            variants.append({
                "fmt": "webp", "w": width, "h": ref_h, "q": q,
                "ssim": webp_ssim, "bytes": webp_out.stat().st_size,
                "ok": webp_ssim >= SSIM_MIN, "url": "/" + webp_out.relative_to(ROOT).as_posix(),
            })
            win.with_suffix(".webp").unlink(missing_ok=True)

            if width < intrinsic and opaque:
                q, score, ok = search_quality(JPG_LADDER, lambda q: encode_try("jpg", q))
                if not win.with_suffix(".jpg").exists():
                    encode_try("jpg", JPG_LADDER[-1])
                    shutil.copy(trial.with_suffix(".jpg"), win.with_suffix(".jpg"))
                jpg_out = src.parent / "r" / f"{src.stem}-{width}.jpg"
                shutil.copy(win.with_suffix(".jpg"), jpg_out)
                jpg_ssim = ssim(jpg_out, ref, work)
                min_ssim = min(min_ssim, jpg_ssim)
                variants.append({
                    "fmt": "jpg", "w": width, "h": ref_h, "q": q,
                    "ssim": jpg_ssim, "bytes": jpg_out.stat().st_size,
                    "ok": jpg_ssim >= SSIM_MIN, "url": "/" + jpg_out.relative_to(ROOT).as_posix(),
                })
                win.with_suffix(".jpg").unlink(missing_ok=True)

    def srcset(fmt: str) -> str:
        parts = []
        for width in widths:
            if fmt == "jpg" and width == intrinsic:
                parts.append(f"{url} {width}w")
                continue
            hit = next((v for v in variants if v["fmt"] == fmt and v["w"] == width), None)
            if hit:
                parts.append(f"{hit['url']} {width}w")
        return ", ".join(parts)

    return {
        "src": url,
        "file": src_str,
        "width": intrinsic,
        "height": intrinsic_h,
        "opaque": opaque,
        "minSsim": min_ssim,
        "variants": variants,
        "manifest": {"w": intrinsic, "h": intrinsic_h, "avif": srcset("avif"), "webp": srcset("webp"), "jpg": srcset("jpg")},
    }


def parse_attrs(tag: str) -> dict[str, str]:
    return {m.group(1).lower(): m.group(2) for m in re.finditer(r'([^\s=/"\']+)\s*=\s*"([^"]*)"', tag)}


def nearest_role(html: str, start: int) -> str:
    markers = (
        ("thumb", 'class="thumbs"'),
        ("card", 'class="card-media"'),
        ("ig", 'class="ig-grid"'),
        ("shot", 'class="shot'),
        ("gallery", 'class="gallery-main'),
    )
    window = html[:start]
    best_at, best = -1, ""
    for role, marker in markers:
        at = window.rfind(marker)
        if at > best_at:
            best_at, best = at, role
    return best


def default_sizes(role: str) -> str:
    return {
        "thumb": THUMB_SIZES,
        "card": CARD_SIZES,
        "ig": IG_SIZES,
        "shot": HERO_SIZES,
        "gallery": GALLERY_SIZES,
    }.get(role, "100vw")


def render_img(src: str, attrs: dict[str, str], jpg_srcset: str, sizes: str) -> str:
    ordered = []
    for key in ("id", "class"):
        if key in attrs:
            ordered.append(f'{key}="{attrs[key]}"')
    ordered.append(f'src="{src}"')
    if jpg_srcset:
        ordered.append(f'srcset="{jpg_srcset}"')
    if sizes:
        ordered.append(f'sizes="{sizes}"')
    if "alt" in attrs:
        ordered.append(f'alt="{attrs["alt"]}"')
    for key in ("width", "height", "loading", "decoding", "fetchpriority"):
        if key in attrs and attrs[key] != "":
            ordered.append(f'{key}="{attrs[key]}"')
    return "<img " + " ".join(ordered) + ">"


def rewrite_html(manifest: dict, roles: dict[str, set]) -> tuple[int, list[str]]:
    changed = 0
    problems = []
    for path in sorted(ROOT.rglob("*.html")):
        text = path.read_text(encoding="utf-8")
        before_ids = [
            (parse_attrs(m.group(0)).get("src", ""), parse_attrs(m.group(0)).get("alt", ""),
             parse_attrs(m.group(0)).get("width", ""), parse_attrs(m.group(0)).get("height", ""))
            for m in IMG_TAG.finditer(text)
        ]

        def replacer(match: re.Match) -> str:
            tag = match.group(0)
            attrs = parse_attrs(tag)
            src = attrs.get("src", "")
            if not src or src.endswith(".svg") or src not in manifest:
                if src and not src.endswith(".svg") and "width" not in attrs:
                    problems.append(f"{path}: {src} has no width/height and no variants")
                return tag
            role = nearest_role(text, match.start())
            if role:
                roles[src].add(role)
            if attrs.get("fetchpriority") == "high" or attrs.get("id") == "main-photo":
                roles[src].add("lcp")
                if "loading" not in attrs:
                    attrs["loading"] = "eager"
            sizes = attrs.get("sizes") or default_sizes(role)
            info = manifest[src]
            img = render_img(src, attrs, info["jpg"], sizes)
            return (
                "<picture>"
                f'<source type="image/avif" srcset="{info["avif"]}" sizes="{sizes}">'
                f'<source type="image/webp" srcset="{info["webp"]}" sizes="{sizes}">'
                f"{img}</picture>"
            )

        new = IMG_TAG.sub(replacer, text)
        # Preload the product hero. On the homepage the mobile LCP element is the
        # lede text, so a second high-priority image preload is not added there.
        hero = re.search(
            r'<picture><source type="image/avif" srcset="([^"]+)" sizes="([^"]+)">(?:(?!</picture>).)*id="main-photo"',
            new,
        )
        preload = '<link rel="preload" href="/assets/fonts/DMSans-var.woff2" as="font" type="font/woff2" crossorigin>'
        if hero and preload in new and 'rel="preload" as="image"' not in new:
            link = (
                f'<link rel="preload" as="image" type="image/avif" imagesrcset="{hero.group(1)}" '
                f'imagesizes="{hero.group(2)}" fetchpriority="high">'
            )
            new = new.replace(preload, preload + "\n" + link, 1)
        after_ids = [
            (parse_attrs(m.group(0)).get("src", ""), parse_attrs(m.group(0)).get("alt", ""),
             parse_attrs(m.group(0)).get("width", ""), parse_attrs(m.group(0)).get("height", ""))
            for m in IMG_TAG.finditer(new)
        ]
        if before_ids != after_ids:
            problems.append(f"{path.name}: img src/alt/width/height changed")
            # Keep going so the diff is inspectable, but record it.
        if new != text:
            path.write_text(new, encoding="utf-8")
            changed += 1
    return changed, problems


def strip_metadata() -> dict:
    files = [
        str(p.relative_to(ROOT))
        for p in (ROOT / "assets").rglob("*")
        if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    ]
    updated = unchanged = 0
    for i in range(0, len(files), 40):
        chunk = files[i:i + 40]
        proc = subprocess.run(
            ["exiftool", "-all=", "-overwrite_original"] + chunk,
            cwd=ROOT, capture_output=True, text=True,
        )
        blob = proc.stdout + proc.stderr
        for line in blob.splitlines():
            if "image files updated" in line:
                updated += int(line.strip().split()[0])
            elif "image files unchanged" in line:
                unchanged += int(line.strip().split()[0])
        if proc.returncode not in (0, 1):
            raise SystemExit(f"exiftool failed: {blob[-500:]}")
    return {"files": len(files), "updated": updated, "unchanged": unchanged}


def rel_path(path: str) -> str:
    candidate = Path(path)
    if candidate.is_absolute():
        return str(candidate.resolve().relative_to(ROOT))
    return path


def pixel_hashes(paths: list[str] | None = None) -> dict[str, list[str]]:
    if paths is None:
        paths = [
            str(p.relative_to(ROOT))
            for p in (ROOT / "assets").rglob("*")
            if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".ico"}
        ]
    groups: dict[str, list[str]] = defaultdict(list)
    for i in range(0, len(paths), 40):
        chunk = paths[i:i + 40]
        proc = subprocess.run(
            ["identify", "-format", "%#\t%i\n"] + chunk,
            cwd=ROOT, capture_output=True, text=True,
        )
        if proc.returncode != 0:
            raise SystemExit(proc.stderr[-500:])
        for line in proc.stdout.splitlines():
            digest, path = line.split("\t", 1)
            groups[rel_path(path)].append(digest)
    return groups


def load_before() -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for line in HASH_BEFORE.read_text().splitlines():
        digest, _w, _h, _op, path = line.split("\t")
        groups[rel_path(path)].append(digest)
    return groups


def card_snapshot(html: str, grid_id: str) -> list[tuple[str, str, str, str]]:
    at = html.find(f'id="{grid_id}"')
    if at < 0:
        return []
    chunk = html[at:at + 200000]
    end = chunk.find("</div></div></section>")
    if end > 0:
        chunk = chunk[:end]
    cards = []
    for art in re.finditer(r"<article\b.*?</article>", chunk):
        block = art.group(0)
        href = re.search(r'href="([^"]+)"', block)
        title = re.search(r'class="card-title">([^<]*)', block)
        badge = re.search(r'class="badge[^"]*">([^<]*)', block)
        src = re.search(r'<img\b[^>]*\bsrc="([^"]+)"', block)
        cards.append((
            href.group(1) if href else "",
            title.group(1) if title else "",
            badge.group(1) if badge else "",
            src.group(1) if src else "",
        ))
    return cards


def select_width(widths: list[int], needed: float) -> int:
    for w in sorted(widths):
        if w >= needed - 0.5:
            return w
    return max(widths)


def main() -> None:
    os.chdir(ROOT)
    print("stripping metadata", flush=True)
    strip_info = strip_metadata()
    before = load_before()
    after = pixel_hashes()
    mismatches = []
    for path, digests in before.items():
        if after.get(path) != digests:
            mismatches.append(path)
    if mismatches:
        raise SystemExit(f"pixel hash changed on {len(mismatches)} files, e.g. {mismatches[:5]}")
    print(f"pixel hashes unchanged ({len(before)} files)", flush=True)

    srcs = []
    seen = set()
    for html_path in ROOT.rglob("*.html"):
        text = html_path.read_text(encoding="utf-8")
        for match in IMG_TAG.finditer(text):
            src = parse_attrs(match.group(0)).get("src", "")
            if not src or src.endswith(".svg") or src in seen:
                continue
            file_path = ROOT / src.lstrip("/")
            if file_path.is_file():
                seen.add(src)
                srcs.append(str(file_path))
    print(f"encoding {len(srcs)} source images", flush=True)
    results = []
    import multiprocessing as mp
    workers = min(4, os.cpu_count() or 2)
    with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("fork")) as pool:
        futures = {pool.submit(process_source, src): src for src in srcs}
        done = 0
        for fut in as_completed(futures):
            done += 1
            src = futures[fut]
            try:
                item = fut.result()
            except Exception as exc:
                raise SystemExit(f"failed {src}: {exc}") from exc
            results.append(item)
            print(f"[{done}/{len(srcs)}] {item['src']} minSSIM={item['minSsim']:.4f}", flush=True)

    manifest = {item["src"]: item["manifest"] for item in results}
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    roles: dict[str, set] = defaultdict(set)
    pages, problems = rewrite_html(manifest, roles)

    misses = []
    ssim_values = []
    for item in results:
        widths = sorted({v["w"] for v in item["variants"] if v["fmt"] == "avif"})
        by_w = {v["w"]: v for v in item["variants"] if v["fmt"] == "avif"}
        role = roles.get(item["src"], set())
        if "lcp" in role:
            kind = "gallery" if "gallery" in role else "shot"
            needed = MOBILE_CSS * MOBILE_DPR * (1 if kind == "gallery" else 0.62)
            chosen = select_width(widths, needed)
            size = by_w[chosen]["bytes"]
            if size >= HERO_BYTES:
                misses.append({"src": item["src"], "role": "hero", "width": chosen, "bytes": size, "target": HERO_BYTES})
        if "card" in role:
            chosen = select_width(widths, 0.48 * MOBILE_CSS * MOBILE_DPR)
            size = by_w[chosen]["bytes"]
            if size >= CARD_BYTES:
                misses.append({"src": item["src"], "role": "card", "width": chosen, "bytes": size, "target": CARD_BYTES})
        for variant in item["variants"]:
            ssim_values.append(variant["ssim"])

    gps = subprocess.run(
        ["exiftool", "-r", "-q", "-if", "$GPSLatitude or $GPSLongitude or $GPSPosition", "-filename", "-gpslatitude", str(ROOT / "assets")],
        capture_output=True, text=True,
    )
    report = {
        "strip": strip_info,
        "pixelHashMismatches": mismatches,
        "htmlPagesRewritten": pages,
        "htmlProblems": problems,
        "minSsim": min(ssim_values) if ssim_values else None,
        "variantCount": sum(len(item["variants"]) for item in results),
        "misses": misses,
        "gpsStdout": gps.stdout.strip(),
        "belowSsim": [
            {"src": item["src"], "fmt": v["fmt"], "w": v["w"], "q": v["q"], "ssim": v["ssim"], "bytes": v["bytes"]}
            for item in results for v in item["variants"] if v["ssim"] < SSIM_MIN
        ],
    }
    # Rails: homepage drop must keep the same cards, order, titles, badges and photo src.
    for rel in ("index.html", "zh/index.html"):
        current = (ROOT / rel).read_text(encoding="utf-8")
        previous = subprocess.run(["git", "show", f"main:{rel}"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        if card_snapshot(current, "drop-grid") != card_snapshot(previous, "drop-grid"):
            problems.append(f"{rel} drop-grid cards changed")
        report.setdefault("drop", {})[rel] = card_snapshot(current, "drop-grid")
    report["htmlProblems"] = problems
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("strip", "minSsim", "variantCount", "misses", "htmlProblems", "belowSsim", "gpsStdout", "htmlPagesRewritten")}, indent=2))


if __name__ == "__main__":
    main()
