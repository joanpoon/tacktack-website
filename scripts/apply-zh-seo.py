#!/usr/bin/env python3
"""Write Traditional Chinese catalog SEO from data/zh-seo.json into /zh/ pages.

Source of truth for reviewed copy is data/zh-seo.json. Each product also gets
a zhType field on data/products.json (the Chinese product noun). A new product
with zhType, and no reviewed entry yet, inherits a title of the form:

    {lead} {model} {zhType} {colour}（{grade}）｜香港 | Tack, tack!

Sold pieces use「已售出：」and do not mention a price. Titles never include a
price. English pages are not edited.

Usage: python3 scripts/apply-zh-seo.py
"""

from __future__ import annotations

import json
import re
from html import escape as html_escape
from html import unescape as html_unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCTS_PATH = ROOT / "data" / "products.json"
SEO_PATH = ROOT / "data" / "zh-seo.json"
SUFFIX = " | Tack, tack!"

# Simplified forms whose Traditional counterparts differ. Shared characters such
# as 只 are omitted so normal Traditional copy is not flagged.
SIMPLIFIED = set(
    "国门为这灯钟买卖后发个来时书车东马鱼鸟龙云电银质产广众华网体点线"
    "达进运还对开关问应从会与于万丽际过实现经长头红绿蓝黄颜挂钩胶页"
    "签价设饰购选货种条发"
)

GRADES = {
    "brand-new": "全新",
    "display": "展示品",
    "excellent": "極佳",
    "good": "良好",
    "fair": "一般",
}

PAGE_TYPES = {"ItemPage", "CollectionPage", "WebPage"}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def simplified_hits(text: str) -> str:
    return "".join(sorted(set(ch for ch in text if ch in SIMPLIFIED)))


def short_title(title: str) -> str:
    return title[: -len(SUFFIX)] if title.endswith(SUFFIX) else title


def lead_for(product: dict) -> str:
    designer = product.get("designer") or ""
    brand = product.get("brand") or ""
    if designer == "Isamu Noguchi" and brand == "AKARI":
        return "野口勇 AKARI"
    if designer == "Yoshitomo Nara" or brand == "Yoshitomo Nara":
        return "奈良美智"
    return brand


def fallback_seo(product: dict) -> dict:
    """Title and description for a product that has zhType but no reviewed copy."""
    zh_type = (product.get("zhType") or "").strip()
    if not zh_type:
        raise SystemExit(f"{product['slug']} needs zhType or an entry in data/zh-seo.json")
    colour = ((product.get("colour") or {}).get("zh") or "").strip()
    grade = GRADES.get((product.get("condition") or {}).get("grade") or "", "")
    model = (product.get("model") or "").strip()
    parts = [lead_for(product), model, zh_type]
    if colour and colour not in model and colour not in zh_type:
        parts.append(colour)
    head = re.sub(r"\s+", " ", " ".join(p for p in parts if p)).strip()
    sold = product.get("status") == "sold"
    on_hold = product.get("status") == "on-hold"
    if sold:
        title = f"已售出：{head}{SUFFIX}"
        description = (
            f"{head}已於 Tack, tack!（香港）售出，頁面沒有標示價錢。"
            "WhatsApp +852 6507 0791 查詢同類貨品。"
        )
    else:
        grade_bit = f"（{grade}）" if grade else ""
        title = f"{head}{grade_bit}｜香港{SUFFIX}"
        price = product.get("price")
        price_bit = f"HK${price:,}，" if isinstance(price, int) else ""
        grade_word = f"{grade}" if grade else ""
        if on_hold and product.get("preorderOpen"):
            stock = "香港現貨已留貨，仍可預購。"
        elif on_hold:
            stock = "香港現貨已留貨。"
        else:
            stock = "香港現貨。"
        description = (
            f"{grade_word}{head}。{price_bit}{stock}"
            "WhatsApp 查詢，Showroom 預約自取或全港送貨。"
        )
    return {"zhType": zh_type, "title": title, "description": description}


def check_copy(label: str, title: str, description: str) -> None:
    blob = title + description
    hits = simplified_hits(blob)
    if hits:
        raise SystemExit(f"{label} contains Simplified characters: {hits}")
    if "HK$" in title or "＄" in title:
        raise SystemExit(f"{label} title includes a price: {title}")
    # Purchase-source names stay out of public SEO. The fragments are joined so the
    # forbidden name is not stored as one searchable token in this file.
    if ("Mo" "MA Design Store") in blob or "成本" in blob:
        raise SystemExit(f"{label} exposes private wording")


def stamp_zh_type(products_text: str, products: list, types: dict) -> str:
    for product in products:
        slug = product["slug"]
        zh_type = types.get(slug)
        if not zh_type:
            continue
        if product.get("zhType") == zh_type:
            continue
        slug_line = f'"slug": "{slug}",\n'
        if slug_line not in products_text:
            raise SystemExit(f"Could not find slug line for {slug}")
        # Keep the slug line's own indent.
        indent = re.search(rf'^([ \t]*)"slug": "{re.escape(slug)}",$', products_text, re.M)
        pad = indent.group(1) if indent else "   "
        block = f'{pad}"slug": "{slug}",\n{pad}"zhType": "{zh_type}",\n'
        products_text = products_text.replace(f'{pad}"slug": "{slug}",\n', block, 1)
        product["zhType"] = zh_type
    return products_text


def set_attr(html: str, pattern: str, value: str) -> str:
    esc = html_escape(value, quote=True)
    new, n = re.subn(pattern, rf"\g<1>{esc}\g<2>", html, count=1)
    if n != 1:
        raise SystemExit(f"Expected one match for {pattern!r}, found {n}")
    return new


def ensure_twitter(html: str, title: str, description: str) -> str:
    if 'name="twitter:title"' in html:
        html = set_attr(html, r'(<meta name="twitter:title" content=")[^"]*(")', title)
        html = set_attr(html, r'(<meta name="twitter:description" content=")[^"]*(")', description)
        return html
    esc_t = html_escape(title, quote=True)
    esc_d = html_escape(description, quote=True)
    block = (
        f'<meta name="twitter:title" content="{esc_t}">\n'
        f'<meta name="twitter:description" content="{esc_d}">\n'
    )
    anchor = '<meta name="twitter:image"'
    if anchor not in html:
        anchor = '<meta property="og:image"'
    if anchor not in html:
        raise SystemExit("No twitter or og image tag to anchor new Twitter tags")
    return html.replace(anchor, block + anchor, 1)


def update_ld(html: str, short: str, description: str, old_description: str) -> str:
    def repl(match: re.Match) -> str:
        data = json.loads(match.group(1))
        nodes = data.get("@graph", [data])
        for node in nodes:
            types = node.get("@type", [])
            if isinstance(types, str):
                types = [types]
            if PAGE_TYPES.intersection(types):
                node["name"] = short
                node["description"] = description
                if "dateModified" in node:
                    node["dateModified"] = "2026-10-17"
            if "Product" in types and node.get("description") == old_description:
                node["description"] = description
        raw = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        return '<script type="application/ld+json">' + raw + "</script>"

    return re.sub(
        r'<script type="application/ld\+json">(.*?)</script>',
        repl,
        html,
        flags=re.S,
    )


def current_meta(html: str) -> tuple[str, str]:
    title = re.search(r"<title>(.*?)</title>", html, re.S)
    desc = re.search(r'<meta name="description" content="([^"]*)"', html)
    if not title or not desc:
        raise SystemExit("Page is missing title or description")
    return html_unescape(title.group(1).strip()), html_unescape(desc.group(1))


def apply_page(path: Path, title: str, description: str) -> tuple[str, str]:
    html = path.read_text(encoding="utf-8")
    old_title, old_description = current_meta(html)
    html = re.sub(
        r"<title>.*?</title>",
        "<title>" + html_escape(title, quote=False) + "</title>",
        html,
        count=1,
        flags=re.S,
    )
    html = set_attr(html, r'(<meta name="description" content=")[^"]*(")', description)
    html = set_attr(html, r'(<meta property="og:title" content=")[^"]*(")', title)
    html = set_attr(html, r'(<meta property="og:description" content=")[^"]*(")', description)
    html = ensure_twitter(html, title, description)
    html = update_ld(html, short_title(title), description, old_description)
    if html != path.read_text(encoding="utf-8"):
        path.write_text(html, encoding="utf-8")
    return old_title, old_description


def self_test() -> None:
    sample = {
        "slug": "example-new-lamp",
        "brand": "&Tradition",
        "designer": "Verner Panton",
        "model": "Flowerpot VP9",
        "zhType": "便攜燈",
        "colour": {"zh": "Swim Blue"},
        "condition": {"grade": "brand-new"},
        "status": "available",
        "price": 1580,
    }
    seo = fallback_seo(sample)
    check_copy(sample["slug"], seo["title"], seo["description"])
    if "便攜燈" not in seo["title"] or "HK$" in seo["title"]:
        raise SystemExit(f"fallback title failed: {seo['title']}")
    if not seo["title"].endswith(SUFFIX) or "｜香港" not in seo["title"]:
        raise SystemExit(f"fallback title shape failed: {seo['title']}")


def main() -> None:
    self_test()
    seo = load_json(SEO_PATH)
    catalog = load_json(PRODUCTS_PATH)
    products = catalog["products"]
    by_slug = {p["slug"]: p for p in products}
    reviewed = seo["products"]
    types = {slug: entry["zhType"] for slug, entry in reviewed.items()}

    missing = [p["slug"] for p in products if p["slug"] not in reviewed and not p.get("zhType")]
    if missing:
        raise SystemExit("Products with neither reviewed SEO nor zhType: " + ", ".join(missing))

    products_text = PRODUCTS_PATH.read_text(encoding="utf-8")
    stamped = stamp_zh_type(products_text, products, types)
    if stamped != products_text:
        PRODUCTS_PATH.write_text(stamped, encoding="utf-8")

    changes = []
    for slug, product in by_slug.items():
        entry = reviewed.get(slug) or fallback_seo(product)
        check_copy(slug, entry["title"], entry["description"])
        path = ROOT / "zh" / "item" / slug / "index.html"
        if not path.exists():
            raise SystemExit(f"Missing page {path}")
        if 'name="robots" content="noindex"' in path.read_text(encoding="utf-8"):
            continue
        if product.get("status") == "on-hold" and "已留貨" not in entry["description"]:
            raise SystemExit(f"{slug} is on hold but the description does not say 已留貨")
        old_title, old_description = apply_page(path, entry["title"], entry["description"])
        if old_title != entry["title"] or old_description != entry["description"]:
            changes.append((slug, old_title, entry["title"], old_description, entry["description"]))

    for rel, entry in seo["pages"].items():
        check_copy(rel, entry["title"], entry["description"])
        path = ROOT / rel
        old_title, old_description = apply_page(path, entry["title"], entry["description"])
        if old_title != entry["title"] or old_description != entry["description"]:
            changes.append((rel, old_title, entry["title"], old_description, entry["description"]))

    print(f"{len(changes)} pages updated")
    for slug, old_t, new_t, old_d, new_d in changes:
        print(f"\n{slug}")
        print(f"  title: {old_t}")
        print(f"     -> {new_t}")
        if old_d != new_d:
            print(f"  desc:  {old_d}")
            print(f"     -> {new_d}")


if __name__ == "__main__":
    main()
