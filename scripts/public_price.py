#!/usr/bin/env python3
"""Keep a selling price over HK$5,000 off every public surface.

Joan, 31 Oct 2026: an item priced over HK$5,000 must never show that price
on tacktackstudio.com. data/products.json is fetched by the site, so the
number cannot stay in the catalogue either. The field is replaced with
priceOnRequest. Cards, product pages, JSON-LD, meta tags, Merchant feeds,
llms files and sitemap-linked pages then say the price is on request.

A price of HK$5,000 itself still shows. Only a price over that line is hidden.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

THRESHOLD = 5000
POR = {
    "en": "Price on request · DM us",
    "zh": "價格請私訊查詢",
}
ROOT = Path(__file__).resolve().parents[1]
CJK = re.compile(r"[\u3400-\u9fff]")
TEXT_SUFFIXES = {".html", ".xml", ".txt", ".json", ".js", ".css", ".md", ".svg", ".webmanifest", ".py"}
LD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
ARTICLE_RE = re.compile(r'<article class="card\b.*?</article>', re.S)
SG_RE = re.compile(r'<a class="sg-item" href="[^"]*"[^>]*>.*?</a>', re.S)
PRICE_SPAN = r"HK\$\s*\d{1,3}(?:,\d{3})+(?:\.\d{2})?|HK\$\s*\d+(?:\.\d{2})?"


@dataclass
class Hidden:
    slug: str
    sku: str
    title_en: str
    title_zh: str
    status: str
    amount: float | None


def numeric_price(product: dict) -> float | None:
    price = product.get("price")
    if isinstance(price, bool) or price is None:
        return None
    if isinstance(price, (int, float)):
        return float(price)
    if isinstance(price, str):
        raw = price.replace("HK$", "").replace(",", "").strip()
        try:
            return float(raw)
        except ValueError:
            return None
    return None


def hides_price(product: dict) -> bool:
    """True when the selling price must not be shown."""
    if product.get("priceOnRequest") is True:
        return True
    amount = numeric_price(product)
    return amount is not None and amount > THRESHOLD


def _whole(amount: float) -> int | None:
    if float(amount).is_integer():
        return int(amount)
    return None


def forms(amount: float) -> list[str]:
    """Decimal and thousands-separated forms of one selling price."""
    if float(amount).is_integer():
        number = int(amount)
        found = [f"{number:,}", str(number)]
    else:
        found = [f"{amount:,.2f}", f"{amount:.2f}"]
    out = []
    for form in found:
        if form not in out:
            out.append(form)
    return out


def amount_patterns(amount: float) -> list[re.Pattern[str]]:
    patterns = []
    for form in forms(amount):
        patterns.append(re.compile(rf"(?<![\d,]){re.escape(form)}(?!\d)"))
        patterns.append(re.compile(rf"(?<![\d,]){re.escape(form)}\.00(?!\d)"))
    return patterns


def _is_deposit_band(text: str, start: int, end: int) -> bool:
    """Deposit schedule copy, not an item's selling price.

    The public pages already say "HK$1,500 to HK$9,999" and "HK$10,000 and above".
    Those bands stay even if a future piece is listed at one of those amounts.
    """
    after = text[end:end + 24]
    before = text[max(0, start - 8):start]
    if re.match(r"(?:\+| ?and above| ?or above| ?或以上)", after, re.I):
        return True
    if re.match(r",\s*a\s+(?:20|30)%", after, re.I):
        return True
    if re.match(r":\s*30%", after):
        return True
    if re.search(r"(?:to|–|-)\s*$", before):
        return True
    return False


def contains_amount(text: str, amount: float) -> bool:
    for pattern in amount_patterns(amount):
        for match in pattern.finditer(text):
            if not _is_deposit_band(text, match.start(), match.end()):
                return True
    return False


def _sub_price(text: str, pattern: str, label: str) -> str:
    def repl(match: re.Match) -> str:
        if _is_deposit_band(text, match.start(), match.end()):
            return match.group(0)
        return label

    return re.sub(pattern, repl, text)


def replace_price_text(text: str, amount: float, label: str) -> str:
    """Replace public money spellings of this selling price. Leave other amounts."""
    for form in forms(amount):
        text = _sub_price(text, rf"HK\$\s*{re.escape(form)}(?!\d)", label)
        text = _sub_price(text, rf"(?<![\d,]){re.escape(form)}(?:\.00)?\s*HKD\b", label)
    return text


def label_for(text: str, lang: str | None) -> str:
    if lang in POR:
        return POR[lang]
    if CJK.search(text):
        return POR["zh"]
    return POR["en"]


def scrub_str(text: str, amounts: list[float], lang: str | None) -> str:
    label = label_for(text, lang)
    for amount in amounts:
        text = replace_price_text(text, amount, label)
    return text


def scrub_in_place(obj, amounts: list[float], lang: str | None = None) -> None:
    if isinstance(obj, dict):
        for key, value in list(obj.items()):
            next_lang = key if key in ("en", "zh") else lang
            if isinstance(value, str):
                obj[key] = scrub_str(value, amounts, next_lang)
            else:
                scrub_in_place(value, amounts, next_lang)
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            if isinstance(value, str):
                obj[index] = scrub_str(value, amounts, lang)
            else:
                scrub_in_place(value, amounts, lang)


def _object_end(text: str, start: int) -> int:
    depth = 0
    in_str = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_str:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_str = False
            continue
        if char == '"':
            in_str = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index + 1
    raise SystemExit("products.json has an unbalanced product object")


def _drop_json_number(block: str, key: str) -> str:
    updated, count = re.subn(
        rf',\s*\n[ \t]*"{key}"\s*:\s*[-+]?\d+(?:\.\d+)?\s*(?=\n\s*}})',
        "",
        block,
        count=1,
    )
    if count:
        return updated
    updated, _count = re.subn(
        rf'\n[ \t]*"{key}"\s*:\s*[-+]?\d+(?:\.\d+)?\s*,',
        "",
        block,
        count=1,
    )
    return updated


def _drop_equal_retail(block: str, amount: float) -> str:
    """A retail figure that is the selling price would republish it."""
    match = re.search(r'"retailPrice"\s*:\s*([-+]?\d+(?:\.\d+)?)', block)
    if not match:
        return block
    try:
        retail = float(match.group(1))
    except ValueError:
        return block
    if abs(retail - amount) >= 1e-9:
        return block
    return _drop_json_number(block, "retailPrice")


def strip_price_fields(text: str, hidden: list[Hidden]) -> str:
    """Replace a public selling price with priceOnRequest. Keep the surrounding file."""
    for item in hidden:
        if item.amount is None and '"price"' not in text:
            continue
        slug_at = text.find(f'"slug": "{item.slug}"')
        if slug_at < 0:
            raise SystemExit(f"Could not find {item.slug} in products.json")
        start = text.rfind("{", 0, slug_at)
        end = _object_end(text, start)
        block = text[start:end]
        if not re.search(r'"price"\s*:', block):
            if '"priceOnRequest"' not in block:
                block = block[:-1] + ', "priceOnRequest": true}'
            text = text[:start] + block + text[end:]
            continue
        if re.search(r'"priceOnRequest"\s*:\s*true', block):
            updated, count = re.subn(
                r',\s*\n[ \t]*"price"\s*:\s*[-+]?\d+(?:\.\d+)?\s*(?=\n\s*})',
                "",
                block,
                count=1,
            )
            if count == 0:
                updated, count = re.subn(
                    r'\n[ \t]*"price"\s*:\s*[-+]?\d+(?:\.\d+)?\s*,',
                    "",
                    block,
                    count=1,
                )
        else:
            updated, count = re.subn(
                r'"price"\s*:\s*[-+]?\d+(?:\.\d+)?',
                '"priceOnRequest": true',
                block,
                count=1,
            )
        if count != 1:
            raise SystemExit(f"Could not hide the selling price for {item.slug}")
        if item.amount is not None:
            updated = _drop_equal_retail(updated, item.amount)
        json.loads(updated)
        text = text[:start] + updated + text[end:]
    return text


def scrub_json_text(text: str, amounts: list[float]) -> str:
    if not amounts:
        return text
    if not any(contains_amount(text, amount) for amount in amounts):
        return text
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return scrub_lines(text, amounts)
    replacements = []

    def walk(obj, lang: str | None) -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                walk(value, key if key in ("en", "zh") else lang)
        elif isinstance(obj, list):
            for value in obj:
                walk(value, lang)
        elif isinstance(obj, str):
            updated = scrub_str(obj, amounts, lang)
            if updated != obj:
                replacements.append((obj, updated))

    walk(data, None)
    replacements.sort(key=lambda pair: len(pair[0]), reverse=True)
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def scrub_lines(text: str, amounts: list[float]) -> str:
    lines = []
    for line in text.split("\n"):
        lines.append(scrub_str(line, amounts, None))
    return "\n".join(lines)


def file_lang(path: Path) -> str:
    rel = path.relative_to(ROOT).as_posix()
    if rel.startswith("zh/") or path.name.endswith("-zh.xml") or path.name == "zh-seo.json":
        return "zh"
    return "en"


def _drop_retail(html: str, label: str) -> str:
    return re.sub(
        rf"(<span>{re.escape(label)}</span>)<span class=\"retail\">.*?</span>",
        r"\1",
        html,
        flags=re.S,
    )


def _replace_slot(html: str, pattern: str, label: str) -> str:
    def repl(match: re.Match) -> str:
        return match.group(1) + label + match.group(2)

    return re.sub(pattern, repl, html, count=1, flags=re.S)


def redact_structured(html: str, item: Hidden, lang: str) -> str:
    """Price slots for one item: cards, size row, and its own product page."""
    label = POR[lang]
    slug = re.escape(item.slug)

    def article(match: re.Match) -> str:
        block = match.group(0)
        if f"/item/{item.slug}/" not in block:
            return block
        block = _replace_slot(
            block,
            rf'(<p class="card-price"><span>)(?:{PRICE_SPAN})(</span>)(?:<span class="retail">.*?</span>)?',
            label,
        )
        return block

    def size_row(match: re.Match) -> str:
        block = match.group(0)
        if not re.search(rf'/item/{slug}/"', block):
            return block
        return _replace_slot(
            block,
            rf'(<span class="sg-price">)(?:{PRICE_SPAN})(</span>)',
            label,
        )

    html = ARTICLE_RE.sub(article, html)
    html = SG_RE.sub(size_row, html)
    return html


def path_is_item(path: Path, slug: str) -> bool:
    return path.name == "index.html" and path.parent.name == slug and path.parent.parent.name == "item"


def redact_pdp(html: str, item: Hidden, lang: str) -> str:
    label = POR[lang]
    html = _replace_slot(
        html,
        rf'(<div class="pdp-price"><span>)(?:{PRICE_SPAN})(</span>)(?:<span class="retail">.*?</span>)?',
        label,
    )
    html = _replace_slot(
        html,
        rf'(<div class="sticky-cta" id="sticky-cta"><div class="p">)(?:{PRICE_SPAN})(<small>)',
        label,
    )
    if item.status != "sold":
        html = re.sub(
            r"(<p id=\"policy-text\">).*?(</p>)",
            lambda match: match.group(1) + label + match.group(2),
            html,
            count=1,
            flags=re.S,
        )
    html = re.sub(r'\n?<meta property="(?:product|og):price:(?:amount|currency)" content="[^"]*">', "", html)
    return strip_offer_prices(html, force=True)


def strip_offer_prices(html: str, amounts: list[float] | None = None, force: bool = False) -> str:
    """Drop Offer price and priceCurrency. Leave the rest of the schema in place."""
    amounts = amounts or []

    def repl(match: re.Match) -> str:
        raw = match.group(1)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return match.group(0)
        changed = False
        nodes = data.get("@graph", [data] if isinstance(data, dict) else [])
        if isinstance(nodes, dict):
            nodes = [nodes]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            types = node.get("@type")
            types = types if isinstance(types, list) else [types]
            if "Product" not in types:
                continue
            offers = node.get("offers")
            if isinstance(offers, dict):
                offer_list = [offers]
            elif isinstance(offers, list):
                offer_list = [offer for offer in offers if isinstance(offer, dict)]
            else:
                continue
            for offer in offer_list:
                price = numeric_price({"price": offer.get("price")})
                hide = force or (price is not None and (price > THRESHOLD or any(price == amount for amount in amounts)))
                if hide and ("price" in offer or "priceCurrency" in offer):
                    offer.pop("price", None)
                    offer.pop("priceCurrency", None)
                    changed = True
        if not changed:
            return match.group(0)
        dumped = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        return '<script type="application/ld+json">' + dumped + "</script>"

    return LD_RE.sub(repl, html)


def strip_price_meta(html: str, amounts: list[float]) -> str:
    def repl(match: re.Match) -> str:
        try:
            amount = float(match.group(1).replace(",", ""))
        except ValueError:
            return match.group(0)
        if amount > THRESHOLD or any(amount == item for item in amounts):
            return ""
        return match.group(0)

    updated = re.sub(r'\n?<meta property="(?:product|og):price:amount" content="([^"]*)">', repl, html)
    if updated != html:
        updated = re.sub(r'\n?<meta property="(?:product|og):price:currency" content="[^"]*">', "", updated)
    return updated


def redact_html(path: Path, html: str, hidden: list[Hidden], amounts: list[float]) -> str:
    lang = file_lang(path)
    if amounts:
        html = scrub_str(html, amounts, lang)
    for item in hidden:
        html = redact_structured(html, item, lang)
        if path_is_item(path, item.slug):
            html = redact_pdp(html, item, lang)
    html = _drop_retail(html, POR[lang])
    html = strip_price_meta(html, amounts)
    if not any(path_is_item(path, item.slug) for item in hidden):
        html = strip_offer_prices(html, amounts, force=False)
    return html


def iter_public_text(root: Path = ROOT):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if ".git" in path.parts or "node_modules" in path.parts:
            continue
        if path.suffix.lower() in TEXT_SUFFIXES:
            yield path


def conceal_catalog(catalog: dict, text: str) -> tuple[list[Hidden], str]:
    """Hide over-threshold selling prices in memory and in the catalogue text."""
    hidden: list[Hidden] = []
    amounts: list[float] = []
    for product in catalog.get("products") or []:
        if not isinstance(product, dict) or not hides_price(product):
            continue
        amount = numeric_price(product)
        stored = amount if amount is not None and amount > THRESHOLD else None
        name = product.get("name") if isinstance(product.get("name"), dict) else {}
        hidden.append(Hidden(
            slug=product.get("slug") or "",
            sku=(product.get("sku") or "").strip(),
            title_en=(name.get("en") or "").strip(),
            title_zh=(name.get("zh") or "").strip(),
            status=product.get("status") or "",
            amount=stored,
        ))
        if stored is not None:
            amounts.append(stored)
        retail = numeric_price({"price": product.get("retailPrice")})
        if stored is not None and retail is not None and abs(retail - stored) < 1e-9:
            product.pop("retailPrice", None)
        product["priceOnRequest"] = True
        product.pop("price", None)
    if amounts:
        scrub_in_place(catalog, amounts)
        text = strip_price_fields(text, [item for item in hidden if item.amount is not None])
        text = scrub_json_text(text, amounts)
        for amount in amounts:
            if contains_amount(text, amount):
                raise SystemExit("products.json still contains a selling price over HK$5000")
    elif any(item.amount is None and hides_price({"priceOnRequest": True, "slug": item.slug}) for item in hidden):
        text = strip_price_fields(text, hidden)
    return hidden, text


def redact_outputs(files: dict[Path, str], hidden: list[Hidden]) -> dict[Path, str]:
    """Apply the rule to generated files and to any other public file that still has the price."""
    if not hidden:
        return files
    amounts = [float(item.amount) for item in hidden if item.amount is not None]
    catalog_path = ROOT / "data" / "products.json"
    updated = dict(files)
    for path, text in list(updated.items()):
        if path == catalog_path or path.suffix.lower() == ".py":
            continue
        if path.suffix.lower() == ".json":
            updated[path] = scrub_json_text(text, amounts)
        elif path.suffix.lower() in {".html", ".xml"}:
            updated[path] = redact_html(path, text, hidden, amounts)
        else:
            updated[path] = scrub_lines(text, amounts)
    seen = set(updated)
    seen.add(catalog_path)
    for path in iter_public_text():
        if path in seen or "scripts" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".json":
            new = scrub_json_text(text, amounts)
        elif path.suffix.lower() in {".html", ".xml"}:
            new = redact_html(path, text, hidden, amounts)
        elif path.suffix.lower() == ".py":
            continue
        else:
            new = scrub_lines(text, amounts)
        if new != text:
            updated[path] = new
    return updated


def leaks(files: dict[Path, str], hidden: list[Hidden], root: Path = ROOT) -> list[str]:
    """Files that still contain a hidden selling price. Empty means the rule holds."""
    amounts = [float(item.amount) for item in hidden if item.amount is not None]
    if not amounts:
        return []
    found = []
    seen = set()

    def check(path: Path, text: str) -> None:
        for amount in amounts:
            if contains_amount(text, amount):
                found.append(path.relative_to(root).as_posix())
                return

    for path, text in files.items():
        seen.add(path.resolve())
        check(path, text)
    for path in iter_public_text(root):
        if path.resolve() in seen:
            continue
        check(path, path.read_text(encoding="utf-8", errors="ignore"))
    return found


def self_test() -> None:
    over = THRESHOLD + 1
    assert hides_price({"price": THRESHOLD}) is False
    assert hides_price({"price": over}) is True
    assert hides_price({"priceOnRequest": True}) is True
    assert hides_price({"price": "1,000"}) is False
    label = POR["en"]
    assert str(over) not in replace_price_text(f"for HK${over:,}.", over, label)
    band = 10 * 1000
    band_copy = (
        f"From HK$1,500 to HK${band - 1:,}, a 30% deposit. HK${band - 1:,}: 30% deposit. "
        f"From HK${band:,}, a 20% deposit. HK${band:,} and above. HK${band:,}+. HK${band:,} 或以上."
    )
    assert replace_price_text(band_copy, band, label) == band_copy
    assert contains_amount(band_copy, band) is False
    assert contains_amount(band_copy, band - 1) is False
    product_sentence = f"Available for HK${band:,}."
    assert label in replace_price_text(product_sentence, band, label)
    assert contains_amount(product_sentence, band) is True
    assert contains_amount(f'"price": {band}', band) is True
    assert POR["zh"] in scrub_str(f"售 HK${over:,}。", [float(over)], "zh")
    block = (
        '{\n   "slug": "sample-lamp",\n'
        f'   "description": {{"en": "A lamp for HK${over:,}.", "zh": "一盞燈 HK${over:,}。"}},\n'
        f'   "price": {over},\n'
        '   "status": "pre-order"\n}'
    )
    catalog = {"products": [{
        "slug": "sample-lamp",
        "sku": "TT-TEST-POR",
        "status": "pre-order",
        "name": {"en": "Sample lamp", "zh": "樣例燈"},
        "description": {"en": f"A lamp for HK${over:,}.", "zh": f"一盞燈 HK${over:,}。"},
        "price": over,
    }]}
    hidden, text = conceal_catalog(catalog, block)
    assert hidden and hidden[0].sku == "TT-TEST-POR"
    assert catalog["products"][0].get("priceOnRequest") is True
    assert "price" not in catalog["products"][0]
    assert not contains_amount(text, over)
    assert "priceOnRequest" in text
    json.loads(text)
    same_retail = {"products": [{
        "slug": "sample-lamp",
        "sku": "TT-TEST-POR",
        "status": "pre-order",
        "name": {"en": "Sample lamp", "zh": "樣例燈"},
        "price": over,
        "retailPrice": over,
    }]}
    same_block = (
        '{\n   "slug": "sample-lamp",\n'
        f'   "price": {over},\n'
        f'   "retailPrice": {over}\n}}'
    )
    _hidden_retail, retail_text = conceal_catalog(same_retail, same_block)
    assert "retailPrice" not in retail_text
    assert "retailPrice" not in same_retail["products"][0]
    assert not contains_amount(retail_text, over)
    other_retail = {"products": [{
        "slug": "sample-lamp",
        "price": over,
        "retailPrice": THRESHOLD,
    }]}
    other_block = (
        '{\n   "slug": "sample-lamp",\n'
        f'   "price": {over},\n'
        f'   "retailPrice": {THRESHOLD}\n}}'
    )
    _hidden_other, other_text = conceal_catalog(other_retail, other_block)
    assert f'"retailPrice": {THRESHOLD}' in other_text
    assert not contains_amount(other_text, over)
    page = (
        '<meta property="product:price:amount" content="%d">\n'
        '<meta property="product:price:currency" content="HKD">\n'
        '<script type="application/ld+json">{"@context":"https://schema.org","@graph":'
        '[{"@type":"Product","name":"Sample lamp","description":"A lamp for HK$%s.",'
        '"offers":{"@type":"Offer","priceCurrency":"HKD","price":%d,"availability":"https://schema.org/PreOrder"}}]}'
        '</script>\n'
        '<div class="pdp-price"><span>HK$%s</span><span class="retail">New retail approx. HK$9,999</span></div>\n'
        '<p id="policy-text">30%% deposit (HK$9) holds it.</p>\n'
        '<div class="sticky-cta" id="sticky-cta"><div class="p">HK$%s<small>Sample lamp</small></div></div>\n'
        '<article class="card"><a href="/item/sample-lamp/"><p class="card-price"><span>HK$%s</span>'
        '<span class="retail">New retail approx. HK$9,999</span></p></a></article>\n'
        '<article class="card"><a href="/item/other/"><p class="card-price"><span>HK$980</span></p></a></article>\n'
    ) % (over, f"{over:,}", over, f"{over:,}", f"{over:,}", f"{over:,}")
    path = ROOT / "item" / "sample-lamp" / "index.html"
    redacted = redact_html(path, page, hidden, [float(over)])
    assert not contains_amount(redacted, over)
    assert "product:price" not in redacted
    assert '"price"' not in redacted
    assert POR["en"] in redacted
    assert "HK$980" in redacted
    sample_card = redacted.split('href="/item/sample-lamp/"')[1].split("</article>")[0]
    assert "HK$" not in sample_card
    assert "product:price" not in redacted
    kept = redact_html(ROOT / "item" / "other" / "index.html", "<p>HK$980</p>", [], [])
    assert kept == "<p>HK$980</p>"


if __name__ == "__main__":
    self_test()
    print("OK")
