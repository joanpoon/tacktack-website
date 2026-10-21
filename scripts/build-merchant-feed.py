#!/usr/bin/env python3
"""Build Google Merchant Center feeds and align PDP Product JSON-LD.

GitHub Pages serves this repository as static files. Nothing rebuilds the
site on publish, so this script writes the feeds and they are committed:

    feeds/google-merchant.xml
    feeds/google-merchant-zh.xml

Run it after data/products.json changes:

    python3 scripts/build-merchant-feed.py

scripts/apply-zh-seo.py, scripts/apply-en-catalog-seo.py and
scripts/apply-offer-shipping.py call it when they refresh pages. Visible
page copy is left as it is. Only Product JSON-LD is updated.

The feed lists pieces that can be bought: Available (in_stock) and Pre-order
(preorder). Sold, on hold, held, ordered, draft, and any other status are
left out. Each item is built from a fixed field list. g:id is the SKU.
g:availability_date is added for a pre-order only when the catalog has a
public date on availabilityDate, availableOn, preorderDate, or
preorderAvailableOn. A product with no manufacturer brand uses the shop
name as g:brand.
"""

from __future__ import annotations

import json
import os
import re
import sys
from html import unescape
from pathlib import Path
from xml.etree import ElementTree
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
PRODUCTS_PATH = ROOT / "data" / "products.json"
FEEDS = ROOT / "feeds"
ORIGIN = "https://tacktackstudio.com"
G = "http://base.google.com/ns/1.0"
SHOP_BRAND = "Tack, tack!"

# Characters that are Simplified where the Traditional form differs.
# Shared characters are omitted so published Traditional copy is not flagged.
SIMPLIFIED = set(
    "国门为这灯钟买卖后发个来时书车东马鱼鸟龙云电银质产广众华网体点线"
    "达进运还对开关问应从会与于万丽际过实现经长头红绿蓝黄颜挂钩胶页"
    "签价设饰购选货种条发"
)

# Google product taxonomy IDs (en-US). 594 is Home & Garden > Lighting.
# The Lamps leaf under it is 4636, path "Home & Garden > Lighting > Lamps".
CATEGORY_BY_TYPE = {
    "便攜燈": "4636",
    "和紙吊燈": "2524",
    "吊燈": "2524",
    "鐘形吊燈": "2524",
    "壁燈": "6073",
    "米紙燈罩": "3185",
    "吊燈電線組": "2956",
    "雙面鐘": "3890",
    "相框": "597",
    "海報": "500044",
    "矽膠製冰盒": "4746",
    "玻璃酒杯": "2712",
    "波浪掛牆鏡": "595",
    "掛鈎": "5707",
    "波浪掛鈎": "5707",
    "波浪掛牆收納": "5708",
}

PUBLIC_DATE_KEYS = (
    "availabilityDate",
    "availableOn",
    "preorderDate",
    "preorderAvailableOn",
)

# Generic words only. Proper names are not stored in the repo.
GENERIC_PRIVATE_TOKENS = ("cost", "supplier", "qty", "成本", "供應商", "供貨商")
LOCAL_PRIVATE_PATTERNS = ROOT / "scripts" / "merchant-private-patterns.local"
PROMO = re.compile(
    r"free[\s-]*delivery"
    r"|(?:december|十二月).{0,48}(?:free|delivery|免運|免送)"
    r"|(?:free|免運).{0,48}(?:december|十二月)",
    re.I,
)
ADDRESS = re.compile(
    r"\b\d{1,4}\s+[A-Za-z][\w'.-]*(?:\s+[A-Za-z][\w'.-]*){0,4}\s+"
    r"(?:Street|St\.|Road|Rd\.|Avenue|Ave\.|Lane|Drive|Floor)\b"
    r"|showroom\s+address",
    re.I,
)
CJK = re.compile(r"[\u3400-\u9fff]")
DATE_ONLY = re.compile(r"\d{4}-\d{2}-\d{2}")

SCHEMA_AVAILABILITY = {
    "in_stock": "https://schema.org/InStock",
    "preorder": "https://schema.org/PreOrder",
    "sold": "https://schema.org/SoldOut",
    "on-hold": "https://schema.org/OutOfStock",
    "ordered": "https://schema.org/OutOfStock",
    "draft": "https://schema.org/OutOfStock",
}
STATUS_REASON = {
    "sold": "Sold",
    "on-hold": "On hold",
    "ordered": "Ordered",
    "draft": "Draft",
}


def normalize_status(status: str | None) -> str:
    text = re.sub(r"[\s_]+", "-", (status or "").strip().lower())
    if text in {"available", "in-stock", "instock"}:
        return "in_stock"
    if text in {"pre-order", "preorder"}:
        return "preorder"
    if text == "sold":
        return "sold"
    if text in {"on-hold", "held", "hold"}:
        return "on-hold"
    if text in {"ordered", "order"}:
        return "ordered"
    if text == "draft":
        return "draft"
    return "other"


def google_condition(grade: str | None) -> str | None:
    text = re.sub(r"[\s_]+", "-", (grade or "").strip().lower())
    if text in {"brand-new", "new", "open-box"}:
        return "new"
    if text in {"excellent", "good", "fair", "display", "pre-loved", "used", "second-hand"}:
        return "used"
    return None


def schema_condition(grade: str | None) -> str | None:
    kind = google_condition(grade)
    if kind == "new":
        return "https://schema.org/NewCondition"
    if kind == "used":
        return "https://schema.org/UsedCondition"
    return None


def localized(value, lang: str) -> str:
    if isinstance(value, dict):
        text = value.get(lang) or ""
    elif isinstance(value, str):
        text = value
    else:
        text = ""
    return re.sub(r"\s+", " ", text).strip()


def plain_html(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", "", fragment)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def extra_private_patterns() -> list[str]:
    """Literal phrases from TT_PRIVATE_PATTERNS or a gitignored local file."""
    found: list[str] = []
    raw = os.environ.get("TT_PRIVATE_PATTERNS", "")
    for part in re.split(r"[\n,]", raw):
        part = part.strip()
        if part:
            found.append(part)
    if LOCAL_PRIVATE_PATTERNS.is_file():
        for line in LOCAL_PRIVATE_PATTERNS.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                found.append(line)
    return found


def private_regex() -> re.Pattern[str]:
    parts = [re.escape(token) for token in GENERIC_PRIVATE_TOKENS]
    parts.extend(re.escape(extra) for extra in extra_private_patterns())
    return re.compile("|".join(parts), re.I)


def feed_block_tokens() -> list[str]:
    tokens = ["cost", "supplier", "qty"]
    tokens.extend(extra.lower() for extra in extra_private_patterns())
    return tokens


def clean_public_copy(text: str) -> str:
    """Keep public sentences. Drop promo lines and private wording."""
    blocked = private_regex()
    parts = re.split(r"(?<=[.!?。！？])\s+", text.strip())
    kept = []
    for part in parts:
        sentence = part.strip()
        if not sentence:
            continue
        if blocked.search(sentence) or PROMO.search(sentence) or ADDRESS.search(sentence):
            continue
        kept.append(sentence)
    return re.sub(r"\s+", " ", " ".join(kept)).strip()


def format_price(value) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if number < 0:
        return None
    if number.is_integer():
        return f"{int(number)} HKD"
    return f"{number:.2f} HKD"


def absolute(url: str) -> str:
    if url.startswith("https://") or url.startswith("http://"):
        return url
    if not url.startswith("/"):
        url = "/" + url
    return ORIGIN + url


def public_date(product: dict, availability: str) -> str | None:
    if availability != "preorder":
        return None
    for key in PUBLIC_DATE_KEYS:
        raw = product.get(key)
        if isinstance(raw, str) and DATE_ONLY.fullmatch(raw.strip()):
            return raw.strip() + "T00:00+0800"
    return None


def hero_image(slug: str, photos: list) -> str | None:
    """Highest-resolution hero already used on the English PDP."""
    page = ROOT / "item" / slug / "index.html"
    candidates: list[tuple[str, int]] = []
    if page.exists():
        html = page.read_text(encoding="utf-8")
        tag = re.search(r'<img\b[^>]*\bid="main-photo"[^>]*>', html)
        if tag:
            src = re.search(r'\ssrc="([^"]+)"', tag.group(0))
            if src:
                candidates.append((src.group(1), 0))
            srcset = re.search(r'\ssrcset="([^"]+)"', tag.group(0))
            if srcset:
                for part in srcset.group(1).split(","):
                    bits = part.strip().split()
                    if not bits:
                        continue
                    width = 0
                    if len(bits) > 1 and bits[-1].endswith("w") and bits[-1][:-1].isdigit():
                        width = int(bits[-1][:-1])
                    candidates.append((bits[0], width))
    if not candidates:
        for photo in photos:
            if isinstance(photo, str) and photo:
                candidates.append((photo, 0))
    if not candidates:
        return None

    def score(item: tuple[str, int]) -> tuple[int, int]:
        url, width = item
        path = ROOT / url.split("?", 1)[0].lstrip("/")
        size = path.stat().st_size if path.is_file() else 0
        return (width, size)

    best = max(candidates, key=score)[0]
    return absolute(best)


def feed_record(product: dict, lang: str) -> tuple[dict | None, str | None, str | None]:
    """Return (item, exclusion reason, brand note)."""
    slug = product.get("slug") or ""
    sku = (product.get("sku") or "").strip()
    status = normalize_status(product.get("status"))
    label = sku or slug
    if status not in {"in_stock", "preorder"}:
        if status == "other":
            return None, f"{label}: status {product.get('status')!r} is not purchasable", None
        return None, f"{label}: {STATUS_REASON[status]}", None
    if not sku:
        kind = "Pre-order" if status == "preorder" else "Available"
        return None, f"{slug}: {kind}, no SKU", None

    title = clean_public_copy(localized(product.get("name"), lang))
    description = clean_public_copy(localized(product.get("description"), lang))
    price = format_price(product.get("price"))
    photos = product.get("photos") if isinstance(product.get("photos"), list) else []
    image = hero_image(slug, photos)
    condition = google_condition((product.get("condition") or {}).get("grade"))
    category = CATEGORY_BY_TYPE.get((product.get("zhType") or "").strip())
    brand = (product.get("brand") or "").strip()
    brand_note = None
    if not brand:
        brand = SHOP_BRAND
        brand_note = f"{sku}: no manufacturer brand in the catalog; g:brand is the shop name"

    missing = []
    if not title:
        missing.append("title")
    if not description:
        missing.append("description")
    if not price:
        missing.append("price")
    if not image:
        missing.append("hero image")
    if not condition:
        missing.append("condition grade")
    if not category:
        missing.append(f"Google category for type {product.get('zhType')!r}")
    if missing:
        return None, f"{label}: missing {', '.join(missing)}", None

    if lang == "zh":
        hits = "".join(sorted(set(ch for ch in title + description if ch in SIMPLIFIED)))
        if hits:
            return None, f"{label}: Traditional Chinese required, found {hits}", None
    elif CJK.search(title) or CJK.search(description):
        return None, f"{label}: English feed copy contains Chinese characters", None

    link = ORIGIN + (f"/zh/item/{slug}/" if lang == "zh" else f"/item/{slug}/")
    item = {
        "id": sku,
        "title": title,
        "description": description,
        "link": link,
        "image_link": image,
        "price": price,
        "availability": status,
        "condition": condition,
        "brand": brand,
        "google_product_category": category,
        "identifier_exists": "no",
    }
    dated = public_date(product, status)
    if dated:
        item["availability_date"] = dated
    return item, None, brand_note


def render_feed(items: list[dict], lang: str) -> str:
    if lang == "zh":
        link = ORIGIN + "/zh/"
        description = "Tack, tack! 香港設計師燈飾及家品。"
    else:
        link = ORIGIN + "/"
        description = "Designer lighting and objects from Tack, tack! in Hong Kong."
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<!-- Generated by scripts/build-merchant-feed.py from data/products.json. Do not edit by hand. -->",
        f'<rss version="2.0" xmlns:g="{G}">',
        "  <channel>",
        f"    <title>{escape(SHOP_BRAND)}</title>",
        f"    <link>{escape(link)}</link>",
        f"    <description>{escape(description)}</description>",
    ]
    order = (
        "id",
        "title",
        "description",
        "link",
        "image_link",
        "price",
        "availability",
        "availability_date",
        "condition",
        "brand",
        "google_product_category",
        "identifier_exists",
    )
    rss_tags = {"title", "description", "link"}
    for item in items:
        lines.append("    <item>")
        for key in order:
            if key not in item:
                continue
            tag = key if key in rss_tags else "g:" + key
            lines.append(f"      <{tag}>{escape(item[key])}</{tag}>")
        lines.append("    </item>")
    lines.extend(["  </channel>", "</rss>", ""])
    return "\n".join(lines)


def assert_feed(path: Path, lang: str) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    if 'xmlns:g="http://base.google.com/ns/1.0"' not in text:
        raise SystemExit(f"{path} is missing the Google namespace")
    lowered = text.lower()
    for token in feed_block_tokens():
        if token and token in lowered:
            raise SystemExit(f"{path} contains a blocked token")
    if ADDRESS.search(text) or PROMO.search(text):
        raise SystemExit(f"{path} contains a private or promo sentence")
    ElementTree.fromstring(text)
    required = (
        "g:id",
        "title",
        "description",
        "link",
        "g:image_link",
        "g:price",
        "g:availability",
        "g:condition",
        "g:brand",
        "g:google_product_category",
        "g:identifier_exists",
    )
    items = []
    for block in re.findall(r"<item>(.*?)</item>", text, re.S):
        fields = dict(re.findall(r"<([g:]?[\w:-]+)>(.*?)</\1>", block, re.S))
        missing = [name for name in required if not fields.get(name)]
        if missing:
            raise SystemExit(f"{path} item missing {missing}")
        if not re.fullmatch(r"\d+(?:\.\d{2})? HKD", fields["g:price"]):
            raise SystemExit(f"{path} bad price {fields['g:price']}")
        if fields["g:availability"] not in {"in_stock", "preorder"}:
            raise SystemExit(f"{path} bad availability {fields['g:availability']}")
        if fields["g:availability"] == "preorder" and "g:availability_date" in fields:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}\+0800", fields["g:availability_date"]):
                raise SystemExit(f"{path} bad availability_date")
        if fields["g:availability"] != "preorder" and "g:availability_date" in block:
            raise SystemExit(f"{path} availability_date on a non pre-order")
        if fields["g:condition"] not in {"new", "used"}:
            raise SystemExit(f"{path} bad condition")
        if fields["g:identifier_exists"] != "no":
            raise SystemExit(f"{path} identifier_exists must be no")
        if lang == "zh" and "/zh/item/" not in fields["link"]:
            raise SystemExit(f"{path} link is not a Traditional Chinese PDP")
        if lang == "en" and "/zh/" in fields["link"]:
            raise SystemExit(f"{path} English feed links to a /zh/ page")
        if lang == "zh":
            hits = "".join(ch for ch in fields["title"] + fields["description"] if ch in SIMPLIFIED)
            if hits:
                raise SystemExit(f"{path} Simplified characters: {hits}")
        elif CJK.search(fields["title"]) or CJK.search(fields["description"]):
            raise SystemExit(f"{path} English item contains Chinese copy")
        items.append(fields)
    if not items:
        raise SystemExit(f"{path} has no items")
    ids = [item["g:id"] for item in items]
    if len(ids) != len(set(ids)):
        raise SystemExit(f"{path} has duplicate ids")
    return items


def page_public_copy(html: str) -> tuple[str, str]:
    h1 = re.search(r"<h1>(.*?)</h1>", html, re.S)
    lede = re.search(r'<p class="pdp-lede">(.*?)</p>', html, re.S)
    name = plain_html(h1.group(1)) if h1 else ""
    description = plain_html(lede.group(1)) if lede else ""
    return name, description


def set_if(obj: dict, key: str, value) -> bool:
    if obj.get(key) != value:
        obj[key] = value
        return True
    return False


def sync_product_node(node: dict, product: dict, lang: str, page_name: str, page_description: str) -> bool:
    changed = False
    name = page_name or localized(product.get("name"), lang)
    description = page_description or localized(product.get("description"), lang)
    if name:
        changed |= set_if(node, "name", name)
    if description:
        changed |= set_if(node, "description", description)
    sku = (product.get("sku") or "").strip()
    if sku:
        changed |= set_if(node, "sku", sku)
    brand = (product.get("brand") or "").strip()
    if brand:
        changed |= set_if(node, "brand", {"@type": "Brand", "name": brand})
    photos = product.get("photos") if isinstance(product.get("photos"), list) else []
    images = [absolute(photo) for photo in photos if isinstance(photo, str) and photo]
    if images:
        changed |= set_if(node, "image", images)
    slug = product["slug"]
    url = ORIGIN + (f"/zh/item/{slug}/" if lang == "zh" else f"/item/{slug}/")
    changed |= set_if(node, "url", url)

    status = normalize_status(product.get("status"))
    availability = SCHEMA_AVAILABILITY.get(status)
    condition = schema_condition((product.get("condition") or {}).get("grade"))
    price = product.get("price")
    if isinstance(price, float) and price.is_integer():
        price = int(price)
    offers = node.get("offers")
    if isinstance(offers, dict):
        offer_list = [offers]
    elif isinstance(offers, list):
        offer_list = [offer for offer in offers if isinstance(offer, dict)]
    else:
        offers = {"@type": "Offer"}
        node["offers"] = offers
        offer_list = [offers]
        changed = True
    for offer in offer_list:
        changed |= set_if(offer, "@type", "Offer")
        changed |= set_if(offer, "url", url)
        if availability:
            changed |= set_if(offer, "availability", availability)
        if condition:
            changed |= set_if(offer, "itemCondition", condition)
        if isinstance(price, (int, float)) and not isinstance(price, bool):
            changed |= set_if(offer, "price", price)
            changed |= set_if(offer, "priceCurrency", "HKD")
    return changed


def product_script(product: dict, lang: str, page_name: str, page_description: str) -> str:
    node = {"@type": "Product"}
    sync_product_node(node, product, lang, page_name, page_description)
    data = {"@context": "https://schema.org", "@graph": [node]}
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return '<script type="application/ld+json">' + raw + "</script>"


def patch_pdp(path: Path, product: dict) -> bool:
    html = path.read_text(encoding="utf-8")
    if 'http-equiv="refresh"' in html or 'content="noindex"' in html and "product-root" not in html:
        return False
    lang = "zh" if "zh" in path.relative_to(ROOT).parts else "en"
    page_name, page_description = page_public_copy(html)
    changed = False

    def repl(match: re.Match) -> str:
        nonlocal changed
        data = json.loads(match.group(1))
        nodes = data.get("@graph")
        if not isinstance(nodes, list):
            return match.group(0)
        touched = False
        for node in nodes:
            if not isinstance(node, dict):
                continue
            types = node.get("@type")
            if types == "Product" or (isinstance(types, list) and "Product" in types):
                if sync_product_node(node, product, lang, page_name, page_description):
                    touched = True
        if not touched:
            return match.group(0)
        changed = True
        raw = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        return '<script type="application/ld+json">' + raw + "</script>"

    if 'type="application/ld+json"' in html:
        new = re.sub(
            r'<script type="application/ld\+json">(.*?)</script>',
            repl,
            html,
            flags=re.S,
        )
    elif 'id="product-root"' in html:
        block = product_script(product, lang, page_name, page_description)
        new = html.replace("</head>", block + "\n</head>", 1)
        changed = new != html
    else:
        return False
    if changed and new != html:
        path.write_text(new, encoding="utf-8")
        return True
    return False


def sync_pages(products: list[dict]) -> list[str]:
    updated = []
    by_slug = {product["slug"]: product for product in products if product.get("slug")}
    for path in sorted(list((ROOT / "item").glob("*/index.html")) + list((ROOT / "zh" / "item").glob("*/index.html"))):
        product = by_slug.get(path.parent.name)
        if not product:
            continue
        if patch_pdp(path, product):
            updated.append(str(path.relative_to(ROOT)))
    return updated


def build_language(products: list[dict], lang: str) -> tuple[list[dict], list[str], list[str]]:
    items = []
    excluded = []
    notes = []
    seen = set()
    for product in products:
        item, reason, note = feed_record(product, lang)
        if reason:
            if lang == "en":
                excluded.append(reason)
            continue
        if item["id"] in seen:
            raise SystemExit(f"Duplicate SKU {item['id']}")
        seen.add(item["id"])
        items.append(item)
        if note and lang == "en":
            notes.append(note)
    items.sort(key=lambda item: item["id"])
    return items, excluded, notes


def write_feeds(products: list[dict]) -> None:
    FEEDS.mkdir(exist_ok=True)
    en_items, excluded, notes = build_language(products, "en")
    zh_items, _, _ = build_language(products, "zh")
    if [item["id"] for item in en_items] != [item["id"] for item in zh_items]:
        raise SystemExit("English and Traditional Chinese feeds list different SKUs")
    en_path = FEEDS / "google-merchant.xml"
    zh_path = FEEDS / "google-merchant-zh.xml"
    en_path.write_text(render_feed(en_items, "en"), encoding="utf-8")
    zh_path.write_text(render_feed(zh_items, "zh"), encoding="utf-8")
    assert_feed(en_path, "en")
    assert_feed(zh_path, "zh")
    print(f"EN {len(en_items)}")
    for item in en_items:
        print(f"  {item['id']} {item['availability']} {item['condition']} {item['price']} {item['google_product_category']}")
    print(f"ZH {len(zh_items)}")
    for item in zh_items:
        print(f"  {item['id']} {item['availability']}")
    print(f"EXCLUDED {len(excluded)}")
    for reason in excluded:
        print(f"  {reason}")
    if notes:
        print("BRAND")
        for note in notes:
            print(f"  {note}")


def self_test() -> None:
    assert normalize_status("available") == "in_stock"
    assert normalize_status("In stock") == "in_stock"
    assert normalize_status("pre-order") == "preorder"
    assert normalize_status("Preorder") == "preorder"
    assert normalize_status("sold") == "sold"
    assert normalize_status("on-hold") == "on-hold"
    assert normalize_status("On hold") == "on-hold"
    assert normalize_status("held") == "on-hold"
    assert normalize_status("Ordered") == "ordered"
    assert normalize_status("draft") == "draft"
    assert normalize_status("mystery") == "other"
    assert google_condition("brand-new") == "new"
    assert google_condition("Brand new") == "new"
    assert google_condition("open-box") == "new"
    assert google_condition("Excellent") == "used"
    assert google_condition("Good") == "used"
    assert google_condition("Fair") == "used"
    assert google_condition("Display") == "used"
    assert google_condition(None) is None
    assert format_price(1328) == "1328 HKD"
    assert format_price(45) == "45 HKD"
    assert escape("&Tradition") == "&amp;Tradition"
    cleaned = clean_public_copy(
        "A green lamp for the table. Unit cost stays off this page. Internal note: example."
    )
    assert "cost" not in cleaned.lower()
    assert cleaned.startswith("A green lamp")
    previous = os.environ.get("TT_PRIVATE_PATTERNS")
    os.environ["TT_PRIVATE_PATTERNS"] = "example-secret"
    try:
        hidden = clean_public_copy("A public lamp. See example-secret for the note.")
        assert "example-secret" not in hidden.lower()
        assert hidden.startswith("A public lamp")
    finally:
        if previous is None:
            os.environ.pop("TT_PRIVATE_PATTERNS", None)
        else:
            os.environ["TT_PRIVATE_PATTERNS"] = previous
    sample = {
        "slug": "sample-lamp",
        "sku": "TT-TEST-0001",
        "status": "pre-order",
        "brand": "&Tradition",
        "zhType": "便攜燈",
        "name": {"en": "Sample & Lamp", "zh": "樣例燈"},
        "description": {"en": "A public sentence.", "zh": "一段公開說明。"},
        "price": 1328,
        "condition": {"grade": "display"},
        "photos": ["/assets/products/sample-lamp/1.jpg"],
        "availabilityDate": "2026-12-01",
    }
    item, reason, _note = feed_record(sample, "en")
    assert reason is None and item is not None
    assert item["availability"] == "preorder"
    assert item["condition"] == "used"
    assert item["availability_date"] == "2026-12-01T00:00+0800"
    assert item["brand"] == "&Tradition"
    assert item["google_product_category"] == "4636"
    assert "cost" not in render_feed([item], "en").lower()
    sold, sold_reason, _note = feed_record({**sample, "status": "sold", "sku": "TT-TEST-0002"}, "en")
    assert sold is None and sold_reason.endswith("Sold")
    held, held_reason, _note = feed_record({**sample, "status": "on-hold"}, "en")
    assert held is None and "On hold" in held_reason
    no_sku, no_sku_reason, _note = feed_record({**sample, "sku": ""}, "en")
    assert no_sku is None and "no SKU" in no_sku_reason


def main() -> None:
    self_test()
    catalog = json.loads(PRODUCTS_PATH.read_text(encoding="utf-8"))
    products = catalog["products"]
    updated = sync_pages(products)
    print(f"PDP schema updated: {len(updated)}")
    for rel in updated:
        print(f"  {rel}")
    write_feeds(products)


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.exit(0)
