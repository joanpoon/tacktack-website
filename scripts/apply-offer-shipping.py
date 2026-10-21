#!/usr/bin/env python3
"""Fill Product offers.shippingDetails with a quoted Hong Kong delivery policy.

Google Merchant listing wants shippingRate and deliveryTime inside
offers.shippingDetails. The shop does not publish a flat delivery fee: the
delivery page says Hong Kong delivery is quoted on WhatsApp before payment.
A limited free-delivery offer is time-boxed and conditional, so this script
does not set shippingRate.value to 0.

deliveryTime is a generic local window (arrange on WhatsApp, then courier or
movers), not a guaranteed arrival date. Pre-order offers use a longer
handling window because those pieces are not already in Hong Kong.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATE = "2026-10-17"

RETURN_POLICY = {
    "@type": "MerchantReturnPolicy",
    "applicableCountry": "HK",
    "returnPolicyCategory": "https://schema.org/MerchantReturnNotPermitted",
}


def delivery_time(preorder: bool) -> dict:
    # Local stock is arranged after the quote. Pre-order waits on air freight,
    # then the same local delivery. The site does not publish a day count.
    handling = (7, 21) if preorder else (1, 7)
    return {
        "@type": "ShippingDeliveryTime",
        "handlingTime": {
            "@type": "QuantitativeValue",
            "minValue": handling[0],
            "maxValue": handling[1],
            "unitCode": "DAY",
        },
        "transitTime": {
            "@type": "QuantitativeValue",
            "minValue": 1,
            "maxValue": 7,
            "unitCode": "DAY",
        },
    }


def shipping_details(zh: bool, preorder: bool) -> dict:
    link = "https://tacktackstudio.com/zh/delivery/" if zh else "https://tacktackstudio.com/delivery/"
    if zh:
        name = "預購後全港送貨（WhatsApp 報價）" if preorder else "全港送貨（WhatsApp 報價）"
        description = (
            "全港送貨於付款前經 WhatsApp 報價。小件可速遞，大型家具由搬運公司運送。"
            "這不是常設免運。限時滿額免運見送貨頁。"
        )
    else:
        name = (
            "Pre-order, then Hong Kong delivery quoted on WhatsApp"
            if preorder
            else "Hong Kong delivery, quoted on WhatsApp"
        )
        description = (
            "Delivery anywhere in Hong Kong is quoted on WhatsApp before you pay. "
            "Small pieces go by courier; large furniture goes by movers. "
            "This is not a standing free-shipping rate. A limited offer is described on the delivery page."
        )
    return {
        "@type": "OfferShippingDetails",
        "name": name,
        "description": description,
        "shippingDestination": {"@type": "DefinedRegion", "addressCountry": "HK"},
        "shippingSettingsLink": link,
        "shippingRate": {"@type": "MonetaryAmount", "currency": "HKD"},
        "deliveryTime": delivery_time(preorder),
    }


def patch_offer(offer: dict, zh: bool) -> bool:
    changed = False
    availability = offer.get("availability") or ""
    if availability.endswith("/Reserved"):
        offer["availability"] = "https://schema.org/OutOfStock"
        changed = True
        availability = offer["availability"]
    if "shippingDetails" not in offer and "price" not in offer:
        return changed
    if "shippingDetails" not in offer:
        return changed
    preorder = availability.endswith("/PreOrder")
    new_details = shipping_details(zh, preorder)
    if offer.get("shippingDetails") != new_details:
        offer["shippingDetails"] = new_details
        changed = True
    if "hasMerchantReturnPolicy" not in offer:
        offer["hasMerchantReturnPolicy"] = RETURN_POLICY
        changed = True
    return changed


def patch_html(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if 'type="application/ld+json"' not in text:
        return False
    zh = "zh" in path.relative_to(ROOT).parts
    changed = False

    def repl(match: re.Match) -> str:
        nonlocal changed
        data = json.loads(match.group(1))
        nodes = data.get("@graph", [data] if isinstance(data, dict) else [])
        touched = False
        for node in nodes:
            if not isinstance(node, dict):
                continue
            types = node.get("@type", [])
            if isinstance(types, str):
                types = [types]
            offers = node.get("offers")
            if "Product" in types and isinstance(offers, dict):
                if patch_offer(offers, zh):
                    touched = True
            if touched and "dateModified" in node and set(types) & {"ItemPage", "WebPage", "CollectionPage"}:
                node["dateModified"] = DATE
        if not touched:
            return match.group(0)
        changed = True
        raw = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        return '<script type="application/ld+json">' + raw + "</script>"

    new = re.sub(r'<script type="application/ld\+json">(.*?)</script>', repl, text, flags=re.S)
    if changed and new != text:
        path.write_text(new, encoding="utf-8")
    return changed


def main() -> None:
    n = 0
    for path in sorted(ROOT.rglob("index.html")):
        if "assets" in path.parts:
            continue
        if patch_html(path):
            n += 1
            print(path.relative_to(ROOT))
    print(f"{n} pages")
    subprocess.check_call([sys.executable, str(ROOT / "scripts" / "build-merchant-feed.py")])


if __name__ == "__main__":
    main()
