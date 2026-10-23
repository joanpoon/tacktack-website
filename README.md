# Tack, tack!
Website for https://tacktackstudio.com

## Google Merchant Center feeds

GitHub Pages publishes the files in this repository. There is no site build on Pages, so the product feeds are generated and committed:

- [feeds/google-merchant.xml](feeds/google-merchant.xml) (English titles, descriptions, and product links)
- [feeds/google-merchant-zh.xml](feeds/google-merchant-zh.xml) (Traditional Chinese titles, descriptions, and `/zh/` product links)

Regenerate both after `data/products.json` changes:

```bash
python3 scripts/build-merchant-feed.py
```

`scripts/apply-zh-seo.py`, `scripts/apply-en-catalog-seo.py`, and `scripts/apply-offer-shipping.py` call that generator after they refresh pages. `scripts/build-pages.py` is what the site script refers to for full page renders, and it is not in this repository, so the generator lives with the scripts that do rewrite pages.

The feed includes pieces that can be bought: Available (`in_stock`) and Pre-order (`preorder`). Sold, on hold, held, ordered, draft, and any other status are left out. `g:id` is the SKU. A pre-order includes `g:availability_date` only when the catalog has a public date (`availabilityDate`, `availableOn`, `preorderDate`, or `preorderAvailableOn`). Titles and descriptions come from the public name and description only. A product with no manufacturer brand uses the shop name as `g:brand`.

Phrases that must stay out of the feeds, beyond the generic checks, can be listed in the `TT_PRIVATE_PATTERNS` environment variable (comma-separated) or in `scripts/merchant-private-patterns.local` (one literal phrase per line). That file is gitignored.

## Public copy (run this before you show Joan)

Banned shop phrases and Joan’s SKU exceptions live in [docs/public-copy-rules.md](docs/public-copy-rules.md). GitHub Actions runs the same check on every pull request.

From the repo root, before you open a PR:

```bash
python3 scripts/check-public-copy.py --all
```

To scan only files you changed against `origin/main`:

```bash
python3 scripts/check-public-copy.py
```

The check fails on unit-comparison lines, site-mechanics hedges, “previously on display”, “no original box”, `花盆燈`, the Japanese middle-dot `・`, raw SKU / 貨號 in body copy, exclusive-dealer claims, and private cost / source / qty / showroom-address lines.

The same script aligns each product page's schema.org Product and Offer JSON-LD (name, description, sku, brand, image, and the offer's price, currency, availability, condition, and url) with the catalog and the copy already on the page. It does not change visible copy. Sold pages use `https://schema.org/SoldOut`.

The feeds are not listed in `sitemap.xml`. They are product data, not web pages, and adding them as sitemap URLs would make Google fetch a non-sitemap file. `robots.txt` leaves `/feeds/` crawlable and notes the feed URLs for Merchant Center.
