# Public copy rules

Source of truth for tacktackstudio.com product and site copy.

Joan locked these on **21 Oct 2026** after rejects on [PR #57](https://github.com/joanpoon/tacktack-website/pull/57) and the follow-up copy cleanup. The checker reads the JSON block at the bottom of this file. Do not add a banned phrase unless Joan re-locks it and this file is updated first.

**23 Oct 2026.** Joan lifted the ban on `with box` / `boxed` / `連盒` next to Brand new / 全新. Her words: "980 is brand new without box 1080 is brand new with box". `Brand new, with box`, `Brand new, without box`, 「全新連盒」, and 「全新，不連盒」 are allowed on any SKU. The `brand-new-boxed` rule and its Flowerpot VP9-only exception are removed.

Live catalog copy lives in:

- `data/products.json` (names, descriptions, details, condition notes)
- `data/zh-seo.json` (Traditional Chinese titles and meta)
- `item/<slug>/index.html` and `zh/item/<slug>/index.html` (PDPs)
- `brand/<slug>/` and `zh/brand/<slug>/` (brand pages)
- `llms.txt` / `llms-full.txt`
- Help and listing pages (`condition/`, `faq/`, `shop/`, homepage, and the `/zh/` twins)

## Before you show Joan

From the repo root:

```bash
python3 scripts/check-public-copy.py --all
```

That is the same check GitHub Actions runs on every pull request (the Action scans files changed against the PR base; `--all` is the local gate before you open a PR).

Scan only what you edited, against `origin/main`:

```bash
python3 scripts/check-public-copy.py
```

A failing run prints the file, the rule id, and the matched phrase. Fix the copy or, if Joan has re-locked an exception, add it to this file.

## Exceptions (Joan-locked)

Use these exact sentences only on the listed public slugs / SKUs. They exist so the checks do not false-hold locked shop language.

### Heller Swell — official dealer

Heller Swell pages may say we are an official dealer. Not exclusive. Not sole.

| Public name | Slug | SKU |
| --- | --- | --- |
| Swell Wall Catchall · White | `heller-swell-white` | `TT-SWE-0001` |
| Swell Mini · Red Orange | `heller-swell-mini-red-orange` | `TT-SWE-0002` |
| Swell Mini · Cream | `heller-swell-mini-cream` | `TT-SWE-0003` |
| Swell Mini · Blue | `heller-swell-mini-blue` | `TT-SWE-0004` |
| Swell Wall Catchall · Red Orange | `heller-swell-red-orange` | `TT-SWE-0007` |
| Swell Wall Catchall · Blue | `heller-swell-blue` | *(no SKU in `data/products.json`)* |

`heller-swell-mini-cream` also keeps the old slug `heller-swell-mini-white`. The Heller brand pages and the `brands.Heller.officialDealer` field in `data/products.json` may use the same line.

Allowed sentence (EN): `Official Heller dealer` (the brand page short form `Official dealer` is the same lock)
Allowed sentence (ZH): `Heller 官方授權經銷商`

## Banned phrases

Clear bans. The checker fails closed on these.

| Rule | Do not write | Notes |
| --- | --- | --- |
| `unit-comparison` | Comparing one unit to another on the same PDP | Other colours in the range are fine. “This Good lamp vs the Excellent one on this page” is not. Applies to product records and `item/` PDPs only. |
| `site-mechanics` | `page stays up with no price`, `confirm rechargeable before you pay`, `no sign noted`, and close variants (`no marks noted`, `stays up with no price`) | Sold pages say the piece found a new home. Do not explain site behaviour. |
| `previously-on-display` | `previously on display`, `was on display`, `曾作展示`, `曾經展示`, `之前展示` | Unless Joan re-locks it. The condition-grade sentence “shown in a showroom or shop” / 「曾於陳列室或店舖展示」 stays. |
| `no-original-box` | `may have no original box`, `no original box`, `可能沒有原盒`, `不附原盒` | Unless Joan re-locks it. |
| `flowerpot-zh-name` | `花盆燈` | House name is **Flowerpot 燈**. |
| `katakana-middle-dot` | `・` (U+30FB) | Use `·` (U+00B7). |
| `raw-sku` | Bare `TT-XXX-0000` codes in public body copy | JSON-LD `sku`, catalog `sku`, and a labeled SKU / 貨號 field stay. Do not drop a code into a caption or story. |
| `exclusive-dealer` | exclusive / sole dealer, 獨家, 唯一授權 | Heller is official, not exclusive. |
| `privacy-cost` | unit cost, our cost, purchase cost, 成本, 進貨價 | Public retail “what does it cost?” is fine. |
| `privacy-source` | bought from, sourced from, supplier, 供應商, 入貨自 | Origin like “Made in Japan” / 「日本直送」 is fine. |
| `privacy-qty` | `qty`, stock quantity, `庫存 3` | “In stock in Hong Kong” / 現貨 is fine. |
| `privacy-address` | showroom address, street-level address | “We share the address when you book” is fine. |

<!-- check-public-copy:rules -->
```json
{
  "locked": "2026-10-21",
  "source": "Joan locks from 21 Oct 2026 rejects on PR #57 and follow-ups",
  "scan": {
    "globs": [
      "data/products.json",
      "data/zh-seo.json",
      "llms.txt",
      "llms-full.txt",
      "index.html",
      "shop/index.html",
      "sold/index.html",
      "product/index.html",
      "condition/index.html",
      "faq/index.html",
      "about/index.html",
      "contact/index.html",
      "delivery/index.html",
      "how-to-buy/index.html",
      "item/**/index.html",
      "brand/**/index.html",
      "category/**/index.html",
      "zh/index.html",
      "zh/shop/index.html",
      "zh/sold/index.html",
      "zh/product/index.html",
      "zh/condition/index.html",
      "zh/faq/index.html",
      "zh/about/index.html",
      "zh/contact/index.html",
      "zh/delivery/index.html",
      "zh/how-to-buy/index.html",
      "zh/item/**/index.html",
      "zh/brand/**/index.html",
      "zh/category/**/index.html"
    ]
  },
  "sku_allowed": [
    "\"sku\"\\s*:\\s*\"TT-[A-Z]{3}-\\d{4}\"",
    "\"name\"\\s*:\\s*\"(?:SKU|貨號)\"\\s*,\\s*\"value\"\\s*:\\s*\"TT-[A-Z]{3}-\\d{4}\"",
    "<dt>\\s*(?:SKU|貨號)\\s*</dt>\\s*<dd>\\s*TT-[A-Z]{3}-\\d{4}\\s*</dd>",
    "(?:SKU|貨號)\\s*[:：]?\\s*TT-[A-Z]{3}-\\d{4}"
  ],
  "exceptions": [
    {
      "id": "heller-dealer",
      "locked": "Official dealer, not exclusive or sole",
      "slugs": [
        "heller-swell-white",
        "heller-swell-mini-red-orange",
        "heller-swell-mini-cream",
        "heller-swell-mini-blue",
        "heller-swell-red-orange",
        "heller-swell-blue",
        "heller-swell-mini-white"
      ],
      "skus": [
        "TT-SWE-0001",
        "TT-SWE-0002",
        "TT-SWE-0003",
        "TT-SWE-0004",
        "TT-SWE-0007"
      ],
      "path_prefixes": [
        "brand/heller/",
        "zh/brand/heller/"
      ],
      "brand_keys": ["Heller"],
      "phrases": [
        "Official Heller dealer",
        "Official dealer",
        "Heller 官方授權經銷商"
      ]
    }
  ],
  "bans": [
    {
      "id": "unit-comparison",
      "scope": "pdp",
      "reason": "Do not compare one unit to another on the same PDP.",
      "patterns": [
        "compared (?:to|with) (?:the )?(?:other|excellent|good|fair|display)",
        "unlike the (?:other|excellent|good|fair|display)",
        "cheaper than the",
        "more (?:marks|wear|scratches) than",
        "this (?:one|piece|lamp|unit) .{0,40} than the (?:other|excellent|good|fair)",
        "比另一[盞件個]",
        "比那[盞件個]",
        "相比另一",
        "另一盞"
      ]
    },
    {
      "id": "site-mechanics",
      "scope": "all",
      "reason": "Do not explain site mechanics on public pages.",
      "patterns": [
        "page stays up",
        "stays up with no price",
        "with no price",
        "confirm rechargeable before you pay",
        "confirm (?:it is )?rechargeable",
        "no sign noted",
        "no signs? (?:were )?noted",
        "no marks?(?: were)? noted",
        "separate listing",
        "頁面會?保留",
        "不標價錢",
        "沒有標價",
        "確認可充電",
        "未見(?:痕跡|記號|劃痕)",
        "沒有記號"
      ]
    },
    {
      "id": "previously-on-display",
      "scope": "all",
      "reason": "Do not say previously on display unless Joan re-locks it.",
      "patterns": [
        "previously on display",
        "previously displayed",
        "was on display",
        "曾作展示",
        "曾經展示",
        "之前展示",
        "先前展示",
        "先前陳列",
        "曾作陳列"
      ]
    },
    {
      "id": "no-original-box",
      "scope": "all",
      "reason": "Do not say the piece may have no original box unless Joan re-locks it.",
      "patterns": [
        "may have no original box",
        "may not have (?:the )?(?:original )?box",
        "no original box",
        "可能沒有原盒",
        "或不附原盒",
        "不附原盒",
        "沒有原盒"
      ]
    },
    {
      "id": "flowerpot-zh-name",
      "scope": "all",
      "reason": "House name is Flowerpot 燈, not 花盆燈.",
      "patterns": ["花盆燈"]
    },
    {
      "id": "katakana-middle-dot",
      "scope": "all",
      "reason": "Use middle dot U+00B7 (·), not katakana middle dot U+30FB (・).",
      "patterns": ["・"]
    },
    {
      "id": "raw-sku",
      "scope": "all",
      "reason": "Raw SKU / 貨號 codes stay out of public body copy.",
      "patterns": [
        "\\bTT-[A-Z]{3}-\\d{4}\\b",
        "貨號\\s*TT-[A-Z]{3}-\\d{4}"
      ]
    },
    {
      "id": "exclusive-dealer",
      "scope": "all",
      "reason": "Heller is an official dealer, not exclusive or sole.",
      "patterns": [
        "exclusive(?:ly)? (?:heller )?dealer",
        "sole(?:\\s+|-)(?:heller )?dealer",
        "獨家(?:授權)?(?:經銷|代理)",
        "唯一授權"
      ]
    },
    {
      "id": "privacy-cost",
      "scope": "all",
      "reason": "Cost price stays private.",
      "patterns": [
        "unit cost",
        "our cost",
        "purchase cost",
        "landed cost",
        "成本",
        "進貨價",
        "入貨價"
      ]
    },
    {
      "id": "privacy-source",
      "scope": "all",
      "reason": "Purchase source and supplier names stay private.",
      "patterns": [
        "bought from",
        "purchased from",
        "sourced from",
        "\\bsupplier\\b",
        "供應商",
        "供貨商",
        "入貨自",
        "購自",
        "買自"
      ]
    },
    {
      "id": "privacy-qty",
      "scope": "all",
      "reason": "Stock quantity stays private.",
      "patterns": [
        "\\bqty\\b",
        "stock quantity",
        "\\d+\\s+(?:units|pcs|pieces) in (?:stock|warehouse)",
        "庫存\\s*\\d",
        "倉庫尚[有餘]"
      ]
    },
    {
      "id": "privacy-address",
      "scope": "all",
      "reason": "Showroom street address stays private.",
      "patterns": [
        "showroom\\s+address",
        "陳列室地址",
        "showroom.{0,24}(?:street|road|avenue|lane|floor)",
        "\\b\\d{1,4}\\s+[A-Za-z][\\w'.-]*(?:\\s+[A-Za-z][\\w'.-]*){0,4}\\s+(?:Street|St\\.|Road|Rd\\.|Avenue|Ave\\.|Lane|Drive|Floor)\\b"
      ]
    }
  ]
}
```
