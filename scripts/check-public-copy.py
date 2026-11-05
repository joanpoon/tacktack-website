#!/usr/bin/env python3
"""Fail public copy that uses Joan-banned phrases.

Rules live in docs/public-copy-rules.md (the JSON block marked
check-public-copy:rules). This script is the gate. It does not rewrite pages.

    python3 scripts/check-public-copy.py --all
    python3 scripts/check-public-copy.py
    python3 scripts/check-public-copy.py --base origin/main

GitHub Actions runs the --base form on every pull request.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES_PATH = ROOT / "docs" / "public-copy-rules.md"
SKIP_JSON_KEYS = {
    "sku",
    "slug",
    "oldSlugs",
    "photos",
    "photo",
    "storyKey",
    "category",
    "status",
    "fulfilment",
    "grade",
    "dropDate",
    "newFrom",
    "availabilityDate",
    "availableOn",
    "preorderDate",
    "preorderAvailableOn",
    "addons",
    "homepageDrop",
    "featured",
    "sizeGuide",
    "photoFit",
    "updated",
}


def load_rules() -> dict:
    text = RULES_PATH.read_text(encoding="utf-8")
    marker = text.find("check-public-copy:rules")
    if marker < 0:
        raise SystemExit(f"No check-public-copy:rules marker in {RULES_PATH}")
    match = re.search(r"```json\n(.*?)```", text[marker:], re.S)
    if not match:
        raise SystemExit(f"No JSON rules block in {RULES_PATH}")
    return json.loads(match.group(1))


def compile_one(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.I | re.S)


def rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def matches_glob(rel_path: str, globs: list[str]) -> bool:
    return any(fnmatch(rel_path, glob) for glob in globs)


def is_pdp_path(rel_path: str) -> bool:
    return bool(re.search(r"(^|/)item/", rel_path))


def slug_from_path(rel_path: str) -> str | None:
    match = re.search(r"(?:^|/)item/([^/]+)/", rel_path)
    return match.group(1) if match else None


def git_names(cmd: list[str]) -> list[str]:
    out = subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True, text=True)
    return [line.strip() for line in out.stdout.splitlines() if line.strip()]


def git_changed(base: str) -> list[str]:
    names = set(git_names(["git", "diff", "--name-only", "--diff-filter=ACMR", f"{base}...HEAD"]))
    names.update(git_names(["git", "diff", "--name-only", "--diff-filter=ACMR", "HEAD"]))
    names.update(git_names(["git", "diff", "--name-only", "--cached", "--diff-filter=ACMR"]))
    names.update(git_names(["git", "ls-files", "--others", "--exclude-standard"]))
    return sorted(names)


def default_base() -> str | None:
    probe = subprocess.run(
        ["git", "rev-parse", "--verify", "origin/main"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if probe.returncode == 0:
        return "origin/main"
    return None


def walk_strings(value, skip_keys: set[str] | None = None):
    skip = skip_keys or set()
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from walk_strings(item, skip)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key in skip:
                continue
            yield from walk_strings(item, skip)


def collect_text(value, skip_keys: set[str] | None = None) -> str:
    return "\n".join(walk_strings(value, skip_keys))


def strip_allowed(text: str, patterns: list[re.Pattern[str]]) -> str:
    cleaned = text
    for pattern in patterns:
        cleaned = pattern.sub(" ", cleaned)
    return cleaned


def exception_phrases(rules: dict, rel_path: str, slug: str | None, brand_key: str | None) -> list[str]:
    found: list[str] = []
    for exc in rules["exceptions"]:
        slugs = set(exc.get("slugs") or [])
        prefixes = exc.get("path_prefixes") or []
        brands = set(exc.get("brand_keys") or [])
        if slug and slug in slugs:
            found.extend(exc.get("phrases") or [])
            continue
        if any(rel_path.startswith(prefix) for prefix in prefixes):
            found.extend(exc.get("phrases") or [])
            continue
        if brand_key and brand_key in brands:
            found.extend(exc.get("phrases") or [])
    return found


def prepare_text(text: str, rules: dict, rel_path: str, slug: str | None, brand_key: str | None) -> str:
    allowed = [compile_one(re.escape(phrase)) for phrase in exception_phrases(rules, rel_path, slug, brand_key)]
    allowed.extend(compile_one(pattern) for pattern in rules.get("sku_allowed") or [])
    return strip_allowed(text, allowed)


def snippet(text: str, start: int, end: int) -> str:
    pad = 24
    chunk = text[max(0, start - pad) : min(len(text), end + pad)]
    return re.sub(r"\s+", " ", chunk).strip()


def scan_text(
    text: str,
    rules: dict,
    rel_path: str,
    where: str,
    slug: str | None = None,
    brand_key: str | None = None,
    scope_pdp: bool | None = None,
) -> list[tuple[str, str, str, str]]:
    if not text:
        return []
    prepared = prepare_text(text, rules, rel_path, slug, brand_key)
    pdp = is_pdp_path(rel_path) if scope_pdp is None else scope_pdp
    hits: list[tuple[str, str, str, str]] = []
    seen: set[tuple[str, str, int]] = set()
    for ban in rules["bans"]:
        if ban.get("scope") == "pdp" and not pdp:
            continue
        for pattern in ban["patterns"]:
            regex = compile_one(pattern)
            for match in regex.finditer(prepared):
                key = (ban["id"], match.group(0), match.start())
                if key in seen:
                    continue
                seen.add(key)
                hits.append((rel_path, where, ban["id"], snippet(prepared, match.start(), match.end())))
    return hits


def scan_html(path: Path, rules: dict) -> list[tuple[str, str, str, str]]:
    rel_path = rel(path)
    return scan_text(path.read_text(encoding="utf-8"), rules, rel_path, "page", slug_from_path(rel_path))


def scan_plain(path: Path, rules: dict) -> list[tuple[str, str, str, str]]:
    rel_path = rel(path)
    return scan_text(path.read_text(encoding="utf-8"), rules, rel_path, "file")


def scan_products(path: Path, rules: dict) -> list[tuple[str, str, str, str]]:
    rel_path = rel(path)
    catalog = json.loads(path.read_text(encoding="utf-8"))
    hits: list[tuple[str, str, str, str]] = []
    for story_key, story in (catalog.get("stories") or {}).items():
        text = collect_text(story)
        hits.extend(scan_text(text, rules, rel_path, f"stories.{story_key}"))
    for brand_key, brand in (catalog.get("brands") or {}).items():
        text = collect_text(brand, SKIP_JSON_KEYS)
        hits.extend(scan_text(text, rules, rel_path, f"brands.{brand_key}", brand_key=brand_key))
    for product in catalog.get("products") or []:
        slug = product.get("slug") or "unknown"
        text = collect_text(product, SKIP_JSON_KEYS)
        hits.extend(
            scan_text(
                text,
                rules,
                rel_path,
                f"products.{slug}",
                slug=slug,
                scope_pdp=True,
            )
        )
    return hits


def scan_zh_seo(path: Path, rules: dict) -> list[tuple[str, str, str, str]]:
    rel_path = rel(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    hits: list[tuple[str, str, str, str]] = []
    for slug, entry in (data.get("products") or {}).items():
        text = collect_text(entry, SKIP_JSON_KEYS)
        hits.extend(
            scan_text(
                text,
                rules,
                rel_path,
                f"products.{slug}",
                slug=slug,
                scope_pdp=True,
            )
        )
    for key, entry in data.items():
        if key in {"_readme", "products"}:
            continue
        text = collect_text(entry, SKIP_JSON_KEYS)
        hits.extend(scan_text(text, rules, rel_path, key))
    return hits


def scan_file(path: Path, rules: dict) -> list[tuple[str, str, str, str]]:
    name = path.name
    if name == "products.json":
        return scan_products(path, rules)
    if name == "zh-seo.json":
        return scan_zh_seo(path, rules)
    if path.suffix == ".html":
        return scan_html(path, rules)
    return scan_plain(path, rules)


def iter_content_files(rules: dict) -> list[Path]:
    globs = rules["scan"]["globs"]
    found: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel_path = rel(path)
        if rel_path.startswith(".git/"):
            continue
        if matches_glob(rel_path, globs):
            found.append(path)
    return sorted(found)


def select_files(rules: dict, base: str | None, scan_all: bool) -> list[Path]:
    if scan_all or not base:
        return iter_content_files(rules)
    chosen: list[Path] = []
    globs = rules["scan"]["globs"]
    for rel_path in git_changed(base):
        if not matches_glob(rel_path, globs):
            continue
        path = ROOT / rel_path
        if path.is_file():
            chosen.append(path)
    return chosen


def print_hits(hits: list[tuple[str, str, str, str]]) -> None:
    print("PUBLIC COPY FAIL")
    print(f"Rules: {RULES_PATH.relative_to(ROOT).as_posix()}")
    for rel_path, where, rule_id, text in hits:
        print(f"  {rel_path} ({where}): {rule_id}: {text}")
    print(f"{len(hits)} hit(s). Fix the copy, or add a Joan-locked exception in docs/public-copy-rules.md.")


def self_test() -> None:
    rules = load_rules()
    dealer = "Official Heller dealer. Heller 官方授權經銷商。"
    slug_swell = "heller-swell-white"

    assert not scan_text("Brand new, with box.", rules, "item/x/index.html", "t", slug="x")
    assert not scan_text("Brand new, without box.", rules, "item/x/index.html", "t", slug="x")
    assert not scan_text("Brand new, boxed.", rules, "item/x/index.html", "t", slug="x")
    assert not scan_text("全新連盒。", rules, "item/x/index.html", "t", slug="x")
    assert not scan_text("全新，不連盒。", rules, "item/x/index.html", "t", slug="x")
    assert not scan_text(dealer, rules, f"item/{slug_swell}/index.html", "t", slug=slug_swell)
    assert not scan_text("Official Heller dealer.", rules, "about/index.html", "t")
    assert scan_text("Exclusive Heller dealer.", rules, f"item/{slug_swell}/index.html", "t", slug=slug_swell)
    assert scan_text("This page stays up with no price.", rules, "item/x/index.html", "t", slug="x")
    assert scan_text("We confirm rechargeable before you pay.", rules, "item/x/index.html", "t", slug="x")
    assert scan_text("No sign noted on the shade.", rules, "item/x/index.html", "t", slug="x")
    assert scan_text("Previously on display in the shop.", rules, "item/x/index.html", "t", slug="x")
    assert scan_text("May have no original box.", rules, "item/x/index.html", "t", slug="x")
    assert scan_text("這是花盆燈。", rules, "item/x/index.html", "t", slug="x")
    assert scan_text("Flowerpot VP9・Matt Black", rules, "item/x/index.html", "t", slug="x")
    assert not scan_text("Flowerpot VP9 · Matt Black", rules, "item/x/index.html", "t", slug="x")
    assert scan_text("This lamp is TT-ANT-0001 in the caption.", rules, "item/x/index.html", "t", slug="x")
    assert not scan_text("貨號 TT-HAY-0009。", rules, "item/x/index.html", "t", slug="x")
    assert not scan_text('<dt>SKU</dt><dd>TT-ANT-0001</dd>', rules, "item/x/index.html", "t", slug="x")
    assert not scan_text('"sku": "TT-ANT-0001"', rules, "item/x/index.html", "t", slug="x")
    assert scan_text("Unit cost was low.", rules, "item/x/index.html", "t", slug="x")
    assert scan_text("Sourced from a warehouse.", rules, "item/x/index.html", "t", slug="x")
    assert scan_text("qty 4 in the back.", rules, "item/x/index.html", "t", slug="x")
    assert scan_text("Showroom address: 12 Example Street", rules, "faq/index.html", "t")
    assert scan_text("Unlike the other excellent lamp, this one is cheaper.", rules, "item/x/index.html", "t", slug="x", scope_pdp=True)
    assert not scan_text("Unlike the other excellent lamp.", rules, "brand/andtradition/index.html", "t")
    assert not scan_text("We quote the cost on WhatsApp before you pay.", rules, "delivery/index.html", "t")
    assert not scan_text("In stock in Hong Kong.", rules, "item/x/index.html", "t", slug="x")
    assert not scan_text("Official Heller dealer.", rules, "data/products.json", "t", brand_key="Heller")


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan public copy for Joan-banned phrases.")
    parser.add_argument("--all", action="store_true", help="Scan every public-copy file.")
    parser.add_argument("--base", help="Git ref to diff against (default: origin/main).")
    parser.add_argument("--skip-self-test", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if not args.skip_self_test:
        self_test()

    rules = load_rules()
    base = args.base
    if not args.all and not base:
        base = default_base()
        if not base:
            args.all = True

    files = select_files(rules, None if args.all else base, args.all)
    hits: list[tuple[str, str, str, str]] = []
    for path in files:
        hits.extend(scan_file(path, rules))

    if hits:
        print_hits(hits)
        return 1

    if args.all:
        print(f"Public copy OK ({len(files)} files).")
    elif not files:
        print("Public copy OK (no content files changed).")
    else:
        print(f"Public copy OK ({len(files)} changed file(s) vs {base}).")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as error:
        sys.stderr.write(error.stderr or str(error))
        sys.exit(1)
    except BrokenPipeError:
        sys.exit(0)
