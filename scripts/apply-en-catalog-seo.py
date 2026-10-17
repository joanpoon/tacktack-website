#!/usr/bin/env python3
"""Tighten thin English titles and a few catalog descriptions.

Traditional Chinese copy is applied separately by scripts/apply-zh-seo.py.
This script only edits English pages, plus the English delivery meta typo.
"""

from __future__ import annotations

import json
import re
from html import escape as html_escape
from html import unescape as html_unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUFFIX = " | Tack, tack!"
DATE = "2026-10-17"

# title, and description only when it should change. None keeps the description.
PAGES = {
    "index.html": (
        None,
        "Hong Kong design shop. In stock: Noguchi AKARI, grey DULTON Double Face wall clock, Nara prints and Flowerpot VP9. Green DULTON: next batch arriving soon, with pre-order.",
    ),
    "shop/index.html": (
        None,
        "Shop designer lighting and decor in Hong Kong: Noguchi AKARI, DULTON Double Face clocks, &Tradition Flowerpot VP9, Heller Swell and Nara prints.",
    ),
    "brand/dulton/index.html": (
        "DULTON Double Face clocks, Hong Kong | Tack, tack!",
        None,
    ),
    "delivery/index.html": (
        None,
        "Showroom pickup by appointment or delivery across Hong Kong, quoted on WhatsApp before you pay. Small pieces by courier, large furniture by movers.",
    ),
    "item/akari-30a/index.html": (
        "Isamu Noguchi AKARI 30A Pendant, Hong Kong | Tack, tack!",
        None,
    ),
    "item/andtradition-flowerpot-vp9-dark-green/index.html": (
        "&Tradition Flowerpot VP9 Dark Green, Hong Kong | Tack, tack!",
        None,
    ),
    "item/andtradition-flowerpot-vp9-matt-black/index.html": (
        "&Tradition Flowerpot VP9 Matt Black, Hong Kong | Tack, tack!",
        None,
    ),
    "item/andtradition-flowerpot-vp9-mustard/index.html": (
        "&Tradition Flowerpot VP9 Mustard, Hong Kong | Tack, tack!",
        None,
    ),
    "item/andtradition-flowerpot-vp9-swim-blue-excellent/index.html": (
        "&Tradition Flowerpot VP9 Swim Blue, Excellent, Hong Kong | Tack, tack!",
        None,
    ),
    "item/andtradition-flowerpot-vp9-swim-blue-good/index.html": (
        "&Tradition Flowerpot VP9 Swim Blue, Good, Hong Kong | Tack, tack!",
        None,
    ),
    "item/andtradition-journey-wall-lamp-shy2/index.html": (
        "&Tradition Journey SHY2 wall lamp, Hong Kong | Tack, tack!",
        None,
    ),
    "item/andtradition-mist-pendant-ap15/index.html": (
        "&Tradition Mist AP15 pendant, Hong Kong | Tack, tack!",
        None,
    ),
    "item/hay-tint-wineglass-clear/index.html": (
        None,
        "HAY Tint wine glasses, set of two, clear. Brand new, with the original box. Sold at Tack, tack! in Hong Kong. No price is shown. WhatsApp +852 6507 0791.",
    ),
    "item/hay-tint-wineglass-pink-yellow/index.html": (
        None,
        "HAY Tint wine glasses, set of two: pink bowls, yellow stems. Brand new, with the original box. Sold at Tack, tack! in Hong Kong. No price is shown. WhatsApp +852 6507 0791.",
    ),
}

LEDE = {
    "index.html": (
        "Curated designer lighting, furniture and objects, new and pre-loved, in stock in Hong Kong: from Isamu Noguchi's paper AKARI to Heller's wave-shaped Swell. This week's drop is the DULTON Double Face wall clock: grey is in stock, and green is on hold with pre-order (Japan air freight). Yoshitomo Nara prints and &amp;Tradition Flowerpot VP9 portable lamps are in the shop too.",
        "Curated designer lighting, furniture and objects, new and pre-loved, in stock in Hong Kong: from Isamu Noguchi's paper AKARI to Heller's wave-shaped Swell. This week's drop is the DULTON Double Face wall clock: grey is in stock, and the next green batch is arriving soon, with pre-order (Japan air freight). Yoshitomo Nara prints and &amp;Tradition Flowerpot VP9 portable lamps are in the shop too.",
    ),
    "zh/index.html": (
        "精選全新及二手設計師燈飾、家具及家品，香港現貨：由野口勇的 AKARI 和紙燈，到 Heller 的波浪 Swell。本週新貨是 DULTON 雙面鐘：灰色是香港現貨，綠色已留貨，仍可預購（日本空運）。店內亦有奈良美智海報及 &amp;Tradition Flowerpot VP9 便攜燈。",
        "精選全新及二手設計師燈飾、家具及家品，香港現貨：由野口勇的 AKARI 和紙燈，到 Heller 的波浪 Swell。本週新貨是 DULTON 雙面鐘：灰色是香港現貨，綠色下一批即將到貨，仍可預購（日本空運）。店內亦有奈良美智海報及 &amp;Tradition Flowerpot VP9 便攜燈。",
    ),
}

TINT = {
    "item/hay-tint-wineglass-clear/index.html": {
        "name": "Tint Wine Glass, set of 2 · Clear",
        "image": "https://tacktackstudio.com/assets/products/hay-tint-wineglass-clear/1.jpg",
        "brand": "HAY",
        "category": "Decor & Objects",
    },
    "item/hay-tint-wineglass-pink-yellow/index.html": {
        "name": "Tint Wine Glass, set of 2 · Pink / Yellow",
        "image": "https://tacktackstudio.com/assets/products/hay-tint-wineglass-pink-yellow/1.jpg",
        "brand": "HAY",
        "category": "Decor & Objects",
    },
    "zh/item/hay-tint-wineglass-clear/index.html": {
        "name": "Tint 酒杯（兩隻裝）· 透明",
        "image": "https://tacktackstudio.com/assets/products/hay-tint-wineglass-clear/1.jpg",
        "brand": "HAY",
        "category": "擺設及家品",
    },
    "zh/item/hay-tint-wineglass-pink-yellow/index.html": {
        "name": "Tint 酒杯（兩隻裝）· 粉紅／黃色",
        "image": "https://tacktackstudio.com/assets/products/hay-tint-wineglass-pink-yellow/1.jpg",
        "brand": "HAY",
        "category": "擺設及家品",
    },
}


def set_attr(html: str, pattern: str, value: str) -> str:
    esc = html_escape(value, quote=True)
    new, n = re.subn(pattern, rf"\g<1>{esc}\g<2>", html, count=1)
    if n != 1:
        raise SystemExit(f"Expected one match for {pattern!r} in a page, found {n}")
    return new


def short_title(title: str) -> str:
    return title[: -len(SUFFIX)] if title.endswith(SUFFIX) else title


def update_ld(html: str, title: str | None, description: str | None) -> str:
    short = short_title(title) if title else None

    def repl(match: re.Match) -> str:
        data = json.loads(match.group(1))
        nodes = data.get("@graph", [data])
        for node in nodes:
            types = node.get("@type", [])
            if isinstance(types, str):
                types = [types]
            if set(types) & {"ItemPage", "CollectionPage", "WebPage"}:
                if short:
                    node["name"] = short
                if description:
                    node["description"] = description
                if "dateModified" in node:
                    node["dateModified"] = DATE
        raw = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        return '<script type="application/ld+json">' + raw + "</script>"

    return re.sub(r'<script type="application/ld\+json">(.*?)</script>', repl, html, count=1, flags=re.S)


def apply_meta(path: Path, title: str | None, description: str | None) -> None:
    html = path.read_text(encoding="utf-8")
    if title:
        html = re.sub(
            r"<title>.*?</title>",
            "<title>" + html_escape(title, quote=False) + "</title>",
            html,
            count=1,
            flags=re.S,
        )
        html = set_attr(html, r'(<meta property="og:title" content=")[^"]*(")', title)
        if 'name="twitter:title"' in html:
            html = set_attr(html, r'(<meta name="twitter:title" content=")[^"]*(")', title)
    if description:
        html = set_attr(html, r'(<meta name="description" content=")[^"]*(")', description)
        html = set_attr(html, r'(<meta property="og:description" content=")[^"]*(")', description)
        if 'name="twitter:description"' in html:
            html = set_attr(html, r'(<meta name="twitter:description" content=")[^"]*(")', description)
    html = update_ld(html, title, description)
    path.write_text(html, encoding="utf-8")


def ensure_tint_product(path: Path, spec: dict) -> None:
    html = path.read_text(encoding="utf-8")
    desc_m = re.search(r'<meta name="description" content="([^"]*)"', html)
    if not desc_m:
        raise SystemExit(f"{path} missing description")
    description = html_unescape(desc_m.group(1))
    rel = path.relative_to(ROOT).as_posix()
    lang = "zh" if rel.startswith("zh/") else "en"
    url_path = "/" + str(path.parent.relative_to(ROOT)).replace("\\", "/") + "/"
    if url_path.startswith("/item/") or url_path.startswith("/zh/"):
        url = "https://tacktackstudio.com" + url_path
    else:
        raise SystemExit(f"Unexpected tint path {rel}")

    def repl(match: re.Match) -> str:
        data = json.loads(match.group(1))
        nodes = data.get("@graph", [])
        if any(n.get("@type") == "Product" for n in nodes if isinstance(n, dict)):
            raw = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
            return '<script type="application/ld+json">' + raw + "</script>"
        product = {
            "@type": "Product",
            "@id": url + "#product",
            "name": spec["name"],
            "description": description,
            "url": url,
            "image": [spec["image"]],
            "brand": {"@type": "Brand", "name": spec["brand"]},
            "category": spec["category"],
            "offers": {
                "@type": "Offer",
                "url": url,
                "availability": "https://schema.org/SoldOut",
                "seller": {
                    "@type": "OnlineStore",
                    "@id": "https://tacktackstudio.com/#org",
                    "name": "Tack, tack!",
                },
                "itemCondition": "https://schema.org/NewCondition",
            },
        }
        nodes.insert(0, product)
        for node in nodes:
            types = node.get("@type", [])
            if isinstance(types, str):
                types = [types]
            if "ItemPage" in types:
                node["mainEntity"] = {"@id": url + "#product"}
                node["description"] = description
                node["dateModified"] = DATE
                node["inLanguage"] = "zh-Hant-HK" if lang == "zh" else "en"
        data["@graph"] = nodes
        raw = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        return '<script type="application/ld+json">' + raw + "</script>"

    html = re.sub(r'<script type="application/ld\+json">(.*?)</script>', repl, html, count=1, flags=re.S)
    path.write_text(html, encoding="utf-8")


def main() -> None:
    for rel, (title, description) in PAGES.items():
        apply_meta(ROOT / rel, title, description)
        print("meta", rel)
    for rel, (old, new) in LEDE.items():
        path = ROOT / rel
        html = path.read_text(encoding="utf-8")
        if old not in html:
            if new in html:
                print("lede already", rel)
                continue
            raise SystemExit(f"Lede not found in {rel}")
        path.write_text(html.replace(old, new, 1), encoding="utf-8")
        print("lede", rel)
    for rel, spec in TINT.items():
        ensure_tint_product(ROOT / rel, spec)
        print("tint", rel)


if __name__ == "__main__":
    main()
