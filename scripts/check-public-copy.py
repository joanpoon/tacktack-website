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
    "variantGroup",
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


def name_to_pattern(name: str) -> str:
    """Match a supplier name with optional spaces or hyphens.

    ASCII names keep word boundaries. A name with any non-ASCII character is a
    substring, because word boundaries do not fall between Chinese characters.
    """
    parts = [re.escape(part) for part in re.split(r"[\s-]+", name.strip()) if part]
    if not parts:
        raise SystemExit(f"Empty supplier name in {RULES_PATH}")
    body = r"[\s-]*".join(parts)
    if all(ord(char) < 128 for char in name):
        return rf"\b{body}\b"
    return body


def ban_patterns(ban: dict) -> list[str]:
    patterns = list(ban.get("patterns") or [])
    patterns.extend(name_to_pattern(name) for name in ban.get("names") or [])
    return patterns


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
        for pattern in ban_patterns(ban):
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
    assert scan_text("貨號 TT-HAY-0009。", rules, "item/x/index.html", "t", slug="x")
    assert not scan_text("貨號：TT-HAY-0009", rules, "item/x/index.html", "t", slug="x")
    assert not scan_text('<dt>SKU</dt><dd>TT-ANT-0001</dd>', rules, "item/x/index.html", "t", slug="x")
    assert not scan_text('<dt>貨號</dt><dd>TT-HAY-0009</dd>', rules, "item/x/index.html", "t", slug="x")
    assert not scan_text('"sku": "TT-ANT-0001"', rules, "item/x/index.html", "t", slug="x")
    assert not scan_text('"name":"貨號","value":"TT-HAY-0009"', rules, "item/x/index.html", "t", slug="x")
    assert not scan_text("(SKU%20TT-ANT-0001)", rules, "item/x/index.html", "t", slug="x")
    assert not scan_text("%E8%B2%A8%E8%99%9F%20TT-HAY-0009", rules, "item/x/index.html", "t", slug="x")
    assert scan_text("We can hold until Friday.", rules, "how-to-buy/index.html", "t")
    assert scan_text("Held up to 7 days.", rules, "how-to-buy/index.html", "t")
    assert scan_text("Up to 14 days.", rules, "how-to-buy/index.html", "t")
    assert not scan_text("Holds up to 7 kg each.", rules, "item/x/index.html", "t", slug="x")
    assert not scan_text("Holds up to 34 kg.", rules, "item/x/index.html", "t", slug="x")
    assert scan_text("保留至下星期五。", rules, "zh/how-to-buy/index.html", "t")
    assert scan_text("最長 14 天。", rules, "zh/how-to-buy/index.html", "t")
    assert scan_text("最多留貨 7 天。", rules, "zh/how-to-buy/index.html", "t")
    assert not scan_text("單個最多承重 7 kg。", rules, "item/x/index.html", "t", slug="x")
    assert scan_text("Under HK$1,500 we take full payment.", rules, "how-to-buy/index.html", "t")
    assert scan_text("Pay a deposit or in full.", rules, "how-to-buy/index.html", "t")
    assert scan_text("HK$10,000 and above: 20% deposit (min. HK$3,000), held up to 14 days.", rules, "how-to-buy/index.html", "t")
    assert scan_text("HK$1,500 以下須全數付款。", rules, "zh/how-to-buy/index.html", "t")
    assert scan_text("付訂金或全數。", rules, "zh/how-to-buy/index.html", "t")
    assert scan_text("50% deposit.", rules, "how-to-buy/index.html", "t")
    assert scan_text("10% 訂金。", rules, "zh/how-to-buy/index.html", "t")
    assert scan_text("a deposit of 20%.", rules, "how-to-buy/index.html", "t")
    assert not scan_text("A 30% deposit reserves every order. The balance is due before pickup or delivery.", rules, "how-to-buy/index.html", "t")
    assert not scan_text("每張訂單付 30% 訂金即可留貨。餘款須於自取或送貨前付清。", rules, "zh/how-to-buy/index.html", "t")
    assert not scan_text("We refund you in full within 2 working days.", rules, "faq/index.html", "t")
    assert not scan_text("訂金將全數退還。我們會於 2 個工作天內全數退款。", rules, "zh/faq/index.html", "t")
    assert not scan_text("Deposits are non-refundable, but they go 100% toward your purchase.", rules, "how-to-buy/index.html", "t")
    assert not scan_text("HK$1,500–5,000", rules, "shop/index.html", "t")
    assert not scan_text("Under HK$500", rules, "shop/index.html", "t")
    assert scan_text("Unit cost was low.", rules, "item/x/index.html", "t", slug="x")
    assert scan_text("Sourced from a warehouse.", rules, "item/x/index.html", "t", slug="x")
    assert scan_text("qty 4 in the back.", rules, "item/x/index.html", "t", slug="x")
    assert scan_text("Showroom address: 12 Example Street", rules, "faq/index.html", "t")
    assert scan_text("Unlike the other excellent lamp, this one is cheaper.", rules, "item/x/index.html", "t", slug="x", scope_pdp=True)
    assert not scan_text("Unlike the other excellent lamp.", rules, "brand/andtradition/index.html", "t")
    assert not scan_text("We quote the cost on WhatsApp before you pay.", rules, "delivery/index.html", "t")
    assert not scan_text("In stock in Hong Kong.", rules, "item/x/index.html", "t", slug="x")
    assert not scan_text("Official Heller dealer.", rules, "data/products.json", "t", brand_key="Heller")

    # 8 Nov 2026 privacy widening. Customer delivery, Made in, and Heller × MoMA stay.
    assert rules["updated"] == "2026-11-08"
    named = next(ban for ban in rules["bans"] if ban["id"] == "privacy-named-supplier")
    assert "Lamp Twist" in named.get("names", [])

    def banned(text: str, rule_id: str, rel_path: str = "item/x/index.html", ruleset: dict | None = None, **kwargs):
        found = scan_text(text, ruleset or rules, rel_path, "t", **kwargs)
        ids = {hit[2] for hit in found}
        assert rule_id in ids, (rule_id, text, found)

    def allowed(text: str, rel_path: str = "item/x/index.html", **kwargs):
        found = scan_text(text, rules, rel_path, "t", **kwargs)
        assert not found, (text, found)

    banned("Ask the vendor before you list it.", "privacy-vendor")
    banned("Two vendors quoted this lamp.", "privacy-vendor")
    banned("向廠商取貨。", "privacy-vendor")
    banned("賣家供應這盞燈。", "privacy-vendor")

    banned("Our freight forwarder has the carton.", "privacy-forwarder")
    banned("The forwarder is late.", "privacy-forwarder")
    banned("Email the freight agent.", "privacy-forwarder")
    banned("貨代已寄出。", "privacy-forwarder")
    banned("經貨運代理付運。", "privacy-forwarder")
    banned("貨運公司取件。", "privacy-forwarder")

    banned("Supplier shipping is extra.", "privacy-supplier-ship")
    banned("Shipped from supplier last week.", "privacy-supplier-ship")
    banned("Shipped from the supplier.", "privacy-supplier-ship")
    banned("Freight from the supplier.", "privacy-supplier-ship")
    banned("供應商出貨日期未定。", "privacy-supplier-ship")
    banned("由供應商運送。", "privacy-supplier-ship")

    for city in ("Osaka", "Copenhagen", "Tokyo", "London", "New York", "Rome", "Paris", "Berlin", "Milan"):
        for verb in ("bought", "purchased", "sourced"):
            banned(f"{verb.capitalize()} in {city}.", "privacy-purchase-place")
    banned("Purchase date: 2024-03-01.", "privacy-purchase-place")
    banned("Bought on 2024-11-08.", "privacy-purchase-place")
    banned("Purchased on 3 March 2024.", "privacy-purchase-place")
    banned("Purchased on March 3, 2024.", "privacy-purchase-place")
    banned("Bought on 8 Nov 2026.", "privacy-purchase-place")
    banned("在大阪購入。", "privacy-purchase-place")
    banned("購於東京。", "privacy-purchase-place")
    banned("入貨日期：2024-11-08。", "privacy-purchase-place")
    banned("2024年入貨。", "privacy-purchase-place")

    banned("Wholesale from a showroom.", "privacy-wholesale")
    banned("We took it at wholesale.", "privacy-wholesale")
    banned("批發自大阪。", "privacy-wholesale")
    banned("批發價入的貨。", "privacy-wholesale")

    banned("From Lamp Twist.", "privacy-named-supplier")
    banned("LampTwist invoice.", "privacy-named-supplier")
    banned("lamp twist stock.", "privacy-named-supplier")
    banned("LAMP-TWIST carton.", "privacy-named-supplier")
    extra = json.loads(json.dumps(rules))
    extra_named = next(ban for ban in extra["bans"] if ban["id"] == "privacy-named-supplier")
    extra_named["names"].append("Secret Mill")
    extra_named["names"].append("秘密工房")
    banned("Carton from Secret Mill.", "privacy-named-supplier", ruleset=extra)
    banned("來自秘密工房。", "privacy-named-supplier", ruleset=extra)
    allowed("Carton from Secret Mill.")
    allowed("來自秘密工房。")

    banned("Bought from MoMA.", "privacy-source")
    banned("Purchased from MoMA.", "privacy-source")
    banned("From MoMA Design Store.", "privacy-source")

    allowed("Local delivery across Hong Kong.")
    allowed("Small pieces can go by courier.")
    allowed("Delivery to your door.")
    allowed("送貨。")
    allowed("本地送貨。")
    allowed("Shipping fee to customer, quoted before you pay.")
    allowed("We quote the cost on WhatsApp before you pay.", "delivery/index.html")
    allowed("Small pieces (lamps, clocks, objects) can go by courier or local delivery. We quote the cost on WhatsApp before you pay.", "delivery/index.html")
    allowed("On hold in Hong Kong. More are available to pre-order: Japan air freight, and we ship it when it lands.", "assets/js/strings.js")
    allowed("Japan air freight. Once it lands in Hong Kong, pick up from the showroom by appointment or we deliver across Hong Kong, quoted on WhatsApp.", "assets/js/strings.js")
    allowed("日本空運。到港後可於 Showroom 預約自取，或全港送貨（運費經 WhatsApp 報價）。", "assets/js/strings.js")
    allowed("小件貨品（燈、掛鍾、擺設等）可安排速遞或本地送貨，運費會在付款前經 WhatsApp 報價。", "zh/delivery/index.html")
    allowed("Made in Japan.")
    allowed("Made in USA.")
    allowed("Made in China.")
    allowed("日本製造。")
    allowed("日本直送。")
    allowed("Official Heller dealer.", f"item/{slug_swell}/index.html", slug=slug_swell)
    allowed("Heller 官方授權經銷商。", f"item/{slug_swell}/index.html", slug=slug_swell)
    allowed("What does it cost?")
    allowed("本店售 HK$148。")
    allowed("In stock in Hong Kong.")
    allowed("香港現貨。")
    allowed("Wholesale lighting for the dining room.")
    allowed("Look at wholesale lighting.")
    allowed("Large furniture goes by movers.")
    allowed("大型家具由搬運公司運送。")
    allowed("New York is a long way from this shade.")
    allowed("MoMA.")
    allowed(
        "Anna Dawson is a RISD-trained designer and California surfer. Heller spotted her Swell prototype at WantedDesign during NYCxDesign in 2022, and a year later launched it at ICFF, in collaboration with MoMA. Its wave-shaped curves have since picked up a Domino decor award (2023) and an Apartment Therapy Small/Cool award (2024). Swell Mini followed in 2025.",
        "data/products.json",
    )
    allowed(
        "Anna Dawson 畢業於 RISD（羅德島設計學院），也是一位加州衝浪愛好者。2022 年 NYCxDesign 期間，Heller 在 WantedDesign 展覽看中她的 Swell 原型，翌年在 ICFF 正式推出，並與 MoMA 合作發佈。這個波浪造型其後獲得 Domino 2023 家居擺設獎及 Apartment Therapy 2024 Small/Cool 獎；2025 年再推出 Swell Mini。",
        "data/products.json",
    )
    allowed("2022 design, launched by Heller 2023.")
    allowed("Bought the lamp for the living room.")


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
