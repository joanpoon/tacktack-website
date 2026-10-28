#!/usr/bin/env python3
"""Build every product list on the site from data/products.json.

GitHub Pages serves static files, so the lists are pre-rendered here and
committed. assets/js/site.js draws the same cards in the browser; the
data-sig fingerprint lets it skip a redraw when nothing has changed.

    python3 scripts/build-lists.py          # write everything
    python3 scripts/build-lists.py --check  # fail if anything is stale or a public piece is unlinked

What it writes:
  * shop, sold, category and brand grids (EN + /zh/) and their ItemList JSON-LD
  * designer hub pages /designer/<slug>/ and /zh/designer/<slug>/ from data/designers.json
  * item and designer entries in sitemap.xml (other URLs are kept as they are)
  * the ## Designers section in llms.txt and llms-full.txt (English name, EN URL
    and English lead, in designers.json order) and the matching links in ## Pages
  * feeds/google-merchant.xml and feeds/google-merchant-zh.xml (via build-merchant-feed.py)

A product is public when published is not false, it has a slug, and its
drop has started: dropAt (ISO time with offset) if set, otherwise dropDate
(HKT day). Renamed slugs (oldSlugs) are redirect pages and are never listed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import functools
import html
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = "https://tacktackstudio.com"
HKT = dt.timezone(dt.timedelta(hours=8))
CATALOG = json.loads((ROOT / "data/products.json").read_text(encoding="utf-8"))
DESIGNERS = json.loads((ROOT / "data/designers.json").read_text(encoding="utf-8"))["designers"]
IMG = json.loads((ROOT / "assets/img-variants.json").read_text(encoding="utf-8"))
_cfg = (ROOT / "assets/js/config.js").read_text(encoding="utf-8")
def _num(key, default):
    m = re.search(key + r":\s*(\d+)", _cfg)
    return int(m.group(1)) if m else default
NEW_DAYS, DROP_HOUR = _num("NEW_DAYS", 7), _num("DROP_HOUR", 20)

# Same strings as assets/js/strings.js
S = {
    "en": {"badge": {"hold": "On hold", "sold": "Sold", "neu": "New this week", "preorder": "Pre-order"},
           "retail": "New retail approx. {}", "illus": " (illustration)"},
    "zh": {"badge": {"hold": "已留貨", "sold": "已售出", "neu": "本週新貨", "preorder": "預購"},
           "retail": "全新參考價約 {}", "illus": "（示意插圖）"},
}
CARD_SIZES = "(min-width: 1100px) 300px, (min-width: 760px) 31vw, 48vw"
NOW = dt.datetime.now(dt.timezone.utc)
TODAY = NOW.astimezone(HKT).date().isoformat()


def parse_at(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def is_public(p: dict) -> bool:
    if p.get("published") is False or not p.get("slug"):
        return False
    if p.get("dropAt"):
        return NOW >= parse_at(p["dropAt"])
    return not p.get("dropDate") or p["dropDate"] <= TODAY


ALL = [p for p in CATALOG["products"] if p.get("published") is not False and p.get("slug")]
PUBLIC = [p for p in ALL if is_public(p)]
REDIRECTS = {s for p in ALL for s in p.get("oldSlugs") or []}


def L(o, lang):
    if not o:
        return ""
    return o if isinstance(o, str) else (o.get(lang) or o.get("en") or "")


def esc(s) -> str:
    return html.escape("" if s is None else str(s), quote=True).replace("&#x27;", "&#39;")


def st(p):
    s = p.get("status")
    return s if s in ("sold", "on-hold", "pre-order") else "available"


def money(n) -> str:
    return "HK${:,}".format(int(n or 0))


def is_new(p) -> bool:
    day = p.get("newFrom") or p.get("dropDate")
    if not day or not re.fullmatch(r"\d{4}-\d\d-\d\d", day):
        return False
    t0 = dt.datetime.fromisoformat(f"{day}T{DROP_HOUR:02d}:00:00+08:00")
    return t0 <= NOW < t0 + dt.timedelta(days=NEW_DAYS)


def photo(p):
    return (p.get("photos") or [None])[0] or "/assets/brand/mark.svg"


def alt(p, lang):
    if re.search(r"placeholder-\d", photo(p)):
        return L(p.get("name"), lang) + S[lang]["illus"]
    return L(p.get("photoAlt"), lang) or L(p.get("name"), lang)


def picture(src, sizes, attrs, lead=""):
    """Same markup as the pre-rendered pages: <img{lead} src srcset sizes{attrs}> inside AVIF/WebP sources."""
    v = IMG.get(src)
    sa = f' sizes="{sizes}"'
    if not v or not v.get("avif"):
        m = re.match(r"^(/assets/products/[^/]+/)([^/]+\.jpg)$", src or "")
        ss = f' srcset="{m.group(1)}m/{m.group(2)} 600w, {src} 1200w" sizes="{sizes}"' if m else ""
        return f'<img{lead} src="{esc(src)}"{ss}{attrs}>'
    return (f'<picture><source type="image/avif" srcset="{v["avif"]}"{sa}>'
            f'<source type="image/webp" srcset="{v["webp"]}"{sa}>'
            f'<img{lead} src="{esc(src)}" srcset="{v["jpg"]}"{sa}{attrs}></picture>')


def dims(p):
    d = p.get("dimensions") or {}
    parts = []
    if d.get("dia"):
        parts.append(f"Ø{d['dia']}")
    for k, lab in (("w", "W"), ("d", "D"), ("h", "H")):
        if d.get(k):
            parts.append(f"{lab} {d[k]}")
    return " × ".join(parts) + " " + (d.get("unit") or "cm") if parts else ""


def kicker(p):
    out = []
    for x in (p.get("brand"), p.get("designer")):
        if x and x not in out:
            out.append(x)
    return " · ".join(out)


def badges(p, lang):
    B, s, out = S[lang]["badge"], st(p), []
    if s == "sold":
        out.append(("sold", B["sold"]))
    elif s == "on-hold":
        out.append(("hold", B["hold"]))
        if p.get("preorderOpen"):
            out.append(("preorder", B["preorder"]))
    elif s == "pre-order":
        out.append(("preorder", B["preorder"]))
    elif is_new(p):
        out.append(("new", B["neu"]))
    return '<div class="badges">' + "".join(f'<span class="badge badge-{k}">{esc(v)}</span>' for k, v in out) + "</div>"


def price_html(p, lang):
    if st(p) == "sold":
        return f'<span class="sold-label">{esc(S[lang]["badge"]["sold"])}</span>'
    r = f'<span class="retail">{esc(S[lang]["retail"].format(money(p["retailPrice"])))}</span>' if p.get("retailPrice") else ""
    return f"<span>{money(p.get('price'))}</span>{r}"


def item_path(p, lang):
    return ("/zh" if lang == "zh" else "") + f"/item/{p['slug']}/"


def card(p, lang, eager):
    contain = p.get("photoFit") == "contain"
    fit = ' class="fit-contain"' if contain else ""
    v = IMG.get(photo(p)) or {}
    box = (f' width="{v["w"]}" height="{v["h"]}"' if v.get("w") else ' width="1400" height="1400"') if contain else ' width="800" height="1000"'
    attrs = f' alt="{esc(alt(p, lang))}"' + box + ("" if eager else ' loading="lazy"') + ' decoding="async"'
    k, dm = kicker(p), dims(p)
    return (f'<article class="card{" is-sold" if st(p) == "sold" else ""}"><a href="{item_path(p, lang)}">'
            f'<div class="card-media">{picture(photo(p), CARD_SIZES, attrs, fit)}{badges(p, lang)}</div>'
            f'<div class="card-body">' + (f'<p class="card-kicker">{esc(k)}</p>' if k else "") +
            f'<h3 class="card-title">{esc(L(p.get("name"), lang))}</h3>' + (f'<p class="card-meta">{esc(dm)}</p>' if dm else "") +
            f'<p class="card-price">{price_html(p, lang)}</p></div></a></article>')


def js_hash(s: str) -> str:
    h = 5381
    b = s.encode("utf-16-le")
    for i in range(0, len(b), 2):
        h = (h * 33 + (b[i] | b[i + 1] << 8)) & 0xFFFFFFFF
    return str(h)


def js_str(v):
    if v is None or v == "" or v is False:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def sig(lst, lang):
    rows = []
    for p in lst:
        sold = st(p) == "sold"
        rows.append(":".join([p["slug"], st(p), "1" if is_new(p) else "0", "0" if sold else js_str(p.get("price") or 0),
                              js_str(p.get("retailPrice")) if p.get("retailPrice") and not sold else "",
                              L(p.get("name"), lang), photo(p)]))
    return js_hash("|".join(rows))


def _cmp_newest(a, b):
    x, y = b.get("dropDate") or "", a.get("dropDate") or ""
    c = (x > y) - (x < y)
    return c or (1 if b.get("featured") else 0) - (1 if a.get("featured") else 0)


def _cmp_sold_last(a, b):
    return ((1 if st(a) == "sold" else 0) - (1 if st(b) == "sold" else 0)) or _cmp_newest(a, b)


def sold_last(lst):
    return sorted(lst, key=functools.cmp_to_key(_cmp_sold_last))


def newest(lst):
    return sorted(lst, key=functools.cmp_to_key(_cmp_newest))


# ---------- grids ----------
GRID_RE = r'(<div class="grid[^"]*" id="{id}"[^>]*>)((?:<article\b.*?</article>)*)</div>'


def set_grid(text, grid_id, lst, lang, eager):
    rx = re.compile(GRID_RE.format(id=re.escape(grid_id)), re.S)
    m = rx.search(text)
    if not m:
        raise SystemExit(f"grid #{grid_id} not found")
    open_tag = m.group(1)
    s = sig(lst, lang)
    open_tag = re.sub(r' data-sig="\d*"', "", open_tag)[:-1] + f' data-sig="{s}">'
    body = "".join(card(p, lang, eager and i < 4) for i, p in enumerate(lst))
    return text[:m.start()] + open_tag + body + "</div>" + text[m.end():]


def set_itemlist(text, lst, lang):
    def repl(m):
        data = json.loads(m.group(1))
        changed = False
        for node in data.get("@graph", [data]):
            me = node.get("mainEntity")
            if isinstance(me, dict) and me.get("@type") == "ItemList":
                old = me.get("itemListElement") or []
                order = list(old[0].keys()) if old else ["@type", "position", "url", "name"]
                new = []
                for i, p in enumerate(lst, 1):
                    vals = {"@type": "ListItem", "position": i, "url": SITE + item_path(p, lang), "name": L(p.get("name"), lang)}
                    new.append({k: vals[k] for k in order if k in vals})
                me["itemListElement"] = new
                changed = True
        if not changed:
            return m.group(0)
        return '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "</script>"
    return re.sub(r'<script type="application/ld\+json">(.*?)</script>', repl, text, flags=re.S)


def lists():
    """(path, grid id, products, eager, itemlist?) for every pre-rendered list."""
    out = []
    active = [p for p in PUBLIC if st(p) != "sold"]
    for lang, pre in (("en", ""), ("zh", "zh/")):
        out.append((ROOT / pre / "shop/index.html", "shop-grid", sold_last(active), True, lang))
        out.append((ROOT / pre / "sold/index.html", "sold-grid", newest([p for p in PUBLIC if st(p) == "sold"]), False, lang))
        for path in sorted((ROOT / pre / "category").glob("*/index.html")):
            out.append((path, "list-grid", sold_last([p for p in PUBLIC if (p.get("category") or "other") == path.parent.name]), True, lang))
        for path in sorted((ROOT / pre / "brand").glob("*/index.html")):
            m = re.search(r'id="list-grid" data-filter-brand="([^"]*)"', path.read_text(encoding="utf-8"))
            brand = html.unescape(m.group(1))
            out.append((path, "list-grid", sold_last([p for p in PUBLIC if p.get("brand") == brand]), True, lang))
        for d in DESIGNERS:
            out.append((ROOT / pre / "designer" / d["slug"] / "index.html", "list-grid", designer_pieces(d), True, lang))
    return out


def designer_pieces(d):
    return sold_last([p for p in PUBLIC if p.get("designer") == d["name"]])


# ---------- designer pages ----------
def designer_page(d, lang):
    zh = lang == "zh"
    tpl = (ROOT / ("zh/" if zh else "") / "brand/yoshitomo-nara/index.html").read_text(encoding="utf-8")
    pre = "/zh" if zh else ""
    path = f"/designer/{d['slug']}/"
    en_url, zh_url = SITE + path, SITE + "/zh" + path
    url = zh_url if zh else en_url
    name = d["zhName"] if zh else d["name"]
    title = L(d["title"], lang) + " | Tack, tack!"
    desc = L(d["description"], lang)
    pieces = designer_pieces(d)
    head = tpl[:tpl.index("<title>")]
    tail = tpl[tpl.index("</script>", tpl.index('<script type="application/ld+json">')) + len("</script>"):]
    og_alt = "Tack, tack! · designer furniture &amp; lighting, new &amp; pre-loved, Hong Kong"
    meta = [
        f"<title>{esc(title)}</title>",
        f'<meta name="description" content="{esc(desc)}">',
        f'<link rel="canonical" href="{url}">',
        f'<link rel="alternate" hreflang="en" href="{en_url}">',
        f'<link rel="alternate" hreflang="zh-Hant-HK" href="{zh_url}">',
        f'<link rel="alternate" hreflang="x-default" href="{en_url}">',
        '<meta property="og:type" content="profile">',
        f'<meta property="og:locale" content="{"zh_HK" if zh else "en_HK"}">',
        f'<meta property="og:locale:alternate" content="{"en_HK" if zh else "zh_HK"}">',
        f'<meta property="og:title" content="{esc(title)}">',
        f'<meta property="og:description" content="{esc(desc)}">',
        f'<meta property="og:url" content="{url}">',
        f'<meta property="og:image" content="{SITE}{og_image(d)}">',
        f'<meta property="og:image:alt" content="{esc(name)} · Tack, tack!">' if pieces else f'<meta property="og:image:alt" content="{og_alt}">',
        f'<meta name="twitter:title" content="{esc(title)}">',
        f'<meta name="twitter:description" content="{esc(desc)}">',
        f'<meta name="twitter:image" content="{SITE}{og_image(d)}">',
    ]
    home, shop = ("主頁", "選購") if zh else ("Home", "Shop")
    designers_lab = "設計師" if zh else "Designers"
    person = {"@type": "Person", "@id": en_url + "#person", "name": d["name"], "jobTitle": L(d["jobTitle"], lang),
              "nationality": L(d["nationality"], lang), "birthDate": d["born"]}
    if zh and d["zhName"] != d["name"]:
        person["alternateName"] = d["zhName"]
    if d.get("died"):
        person["deathDate"] = d["died"]
    graph = [
        {"@type": "ProfilePage", "@id": url + "#page", "name": L(d["title"], lang), "description": desc, "url": url,
         "inLanguage": "zh-Hant-HK" if zh else "en", "isPartOf": {"@id": SITE + "/#website"}, "dateModified": TODAY,
         "mainEntity": person,
         "hasPart": {"@type": "ItemList", "itemListElement": [
             {"@type": "ListItem", "position": i, "url": SITE + item_path(p, lang), "name": L(p.get("name"), lang)} for i, p in enumerate(pieces, 1)]}},
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": home, "item": SITE + pre + "/"},
            {"@type": "ListItem", "position": 2, "name": shop, "item": SITE + pre + "/shop/"},
            {"@type": "ListItem", "position": 3, "name": name, "item": url}]},
    ]
    ld = '<script type="application/ld+json">' + json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False, separators=(",", ":")) + "</script>"
    head_html = head + "\n".join(meta) + "\n" + ld
    body = tail
    # language toggle points at this page in the other language
    body = re.sub(r'(<a class="lang-toggle" data-lang-toggle href=")[^"]*"', lambda m: m.group(1) + (path if zh else "/zh" + path) + '"', body, count=1)
    main_start, main_end = body.index('<main id="main">'), body.index("</main>") + len("</main>")
    sep = '<span aria-hidden="true">/</span>'
    lines = L(d["story"], lang)
    story = "".join(f"<p>{esc(x)}</p>" for x in lines)
    brand_link = f'<a href="{pre}/brand/{d["brandSlug"]}/">{esc(L(d["brandLabel"], lang))}</a>'
    more = []
    if d.get("extraLink"):
        more.append(f'<a href="{pre}/item/{d["extraLink"]["slug"]}/">{esc(L(d["extraLink"], lang))}</a>')
    more.append(brand_link)
    more_lab = "延伸閱讀： " if zh else "More: "
    grid_attr = f'data-filter-designer="{esc(d["name"])}"'
    others = " · ".join(f'<a href="{pre}/designer/{x["slug"]}/">{esc(x["zhName"] if zh else x["name"])}</a>' for x in DESIGNERS if x is not d)
    main = (
        '<main id="main">\n  <div class="wrap">\n'
        f'    <nav class="crumbs" aria-label="{"導覽路徑" if zh else "Breadcrumb"}"><a href="{pre}/">{home}</a>{sep}<a href="{pre}/shop/">{shop}</a>{sep}<span aria-current="page">{esc(name)}</span></nav>\n'
        '    <header class="page-head">\n'
        f'      <p class="eyebrow">{"設計師" if zh else "Designer"}</p>\n'
        f'      <h1>{esc(name)}</h1>\n'
        f'      <p>{esc(L(d["lead"], lang))}</p>\n'
        '    </header>\n'
        f'    <section class="section-tight"><div class="story"><div><p class="eyebrow">{"設計故事" if zh else "The story"}</p><h2>{esc(name)}</h2></div><div class="story-body">{story}</div></div></section>\n'
        f'    <div class="grid grid-4" id="list-grid" {grid_attr}></div>\n'
        f'    <p class="muted shop-browse">{more_lab}{" · ".join(more)}<br>{"其他設計師： " if zh else "Other designers: "}{others}</p>\n'
        f'    <p style="margin-top:22px"><a class="text-link" href="{pre}/shop/">{"瀏覽全部" if zh else "Shop all"} →</a></p>\n'
        '  </div>\n  <div class="section-tight"></div>\n</main>'
    )
    body = body[:main_start] + main + body[main_end:]
    out = head_html + body
    # same wording as the site-wide 睇貨 fix (書面語)
    out = out.replace("Showroom 睇貨須預約", "Showroom 看貨須預約").replace("聯絡及 Showroom 睇貨", "聯絡及 Showroom 預約看貨")
    return set_grid(out, "list-grid", pieces, lang, True)


def og_image(d):
    pieces = designer_pieces(d)
    for p in pieces:
        if st(p) != "sold":
            return photo(p)
    return pieces[0] and photo(pieces[0]) if pieces else "/assets/brand/og-default.png"


# ---------- designer links on item + brand pages ----------
DESIGNER_LINE_RE = re.compile(r'<br><span class="designer-links">.*?</span>')


def designer_links_html(ds, lang):
    pre = "/zh" if lang == "zh" else ""
    lab = "設計師故事： " if lang == "zh" else "Designer story: "
    return '<br><span class="designer-links">' + lab + " · ".join(
        f'<a href="{pre}/designer/{d["slug"]}/">{esc(d["zhName"] if lang == "zh" else d["name"])}</a>' for d in ds) + "</span>"


def add_designer_links(text, ds, lang):
    text = DESIGNER_LINE_RE.sub("", text)
    if not ds:
        return text
    m = re.search(r'(<p class="muted shop-browse">.*?)(</p>)', text, re.S)
    if not m:
        return text
    block = m.group(1)
    cut = block.find('<br><a href="' + ("/zh" if lang == "zh" else "") + '/condition/"')   # PDP: same spot as discoverLinks() in site.js
    at = m.start(1) + cut if cut >= 0 else m.start(2)
    return text[:at] + designer_links_html(ds, lang) + text[at:]


# ---------- sitemap ----------
def sitemap_block(path, lastmod):
    en, zh = SITE + path, SITE + "/zh" + path
    alts = (f'    <xhtml:link rel="alternate" hreflang="en" href="{en}"/>\n'
            f'    <xhtml:link rel="alternate" hreflang="zh-Hant-HK" href="{zh}"/>\n'
            f'    <xhtml:link rel="alternate" hreflang="x-default" href="{en}"/>\n')
    return "".join(f"  <url>\n    <loc>{u}</loc>\n{alts}    <lastmod>{lastmod}</lastmod>\n  </url>\n" for u in (en, zh))


def build_sitemap(text):
    """Keep every non-item URL and the existing order; item and designer URLs follow the catalogue."""
    want = {}
    for p in PUBLIC:
        if p["slug"] not in REDIRECTS:
            want[f"/item/{p['slug']}/"] = p.get("dropDate") or TODAY
    for d in DESIGNERS:
        want[f"/designer/{d['slug']}/"] = TODAY
    out, done = [], set()
    for b in re.findall(r"  <url>\n.*?</url>\n", text, re.S):
        loc = re.search(r"<loc>([^<]+)</loc>", b).group(1)
        path = re.sub(r"^" + re.escape(SITE) + r"(/zh)?", "", loc)
        if re.match(r"^/(item|designer)/", path) and path not in want:
            continue   # unpublished, redirect, or gated: leave it out
        out.append(b)
        done.add(path)
    for path, lastmod in want.items():
        if path not in done:
            out.append(sitemap_block(path, lastmod))
    return text[:text.index("  <url>")] + "".join(out) + "</urlset>\n"


# ---------- llms.txt / llms-full.txt ----------
def _section_match(text, heading):
    """From a `## heading` line through the next `## ` heading, or to EOF."""
    return re.search(rf"^## {re.escape(heading)}[ \t]*\n.*?(?=^## |\Z)", text, re.M | re.S)


def _put_section(text, heading, body):
    """Replace one section. body includes its heading and a trailing newline."""
    m = _section_match(text, heading)
    if not m:
        return None
    block = body if body.endswith("\n") else body + "\n"
    if text[m.end():].startswith("## "):
        block += "\n"
    return text[:m.start()] + block + text[m.end():]


def designer_llms_lines():
    """One English bullet per designer: name, EN hub URL, English lead."""
    lines = []
    for d in DESIGNERS:
        url = f"{SITE}/designer/{d['slug']}/"
        lead = L(d.get("lead"), "en").strip()
        lines.append(f"- [{d['name']}]({url}): {lead}" if lead else f"- [{d['name']}]({url})")
    return lines


def designers_section_body():
    return "## Designers\n" + "\n".join(designer_llms_lines()) + "\n"


def sync_designers_section(text):
    """Rewrite ## Designers from DESIGNERS, or insert it after ## Brands."""
    replaced = _put_section(text, "Designers", designers_section_body())
    if replaced is not None:
        return replaced
    brands = _section_match(text, "Brands")
    if not brands:
        return text
    block = designers_section_body()
    if text[brands.end():].startswith("## "):
        block += "\n"
    return text[:brands.end()] + block + text[brands.end():]


# A Pages bullet whose link is the EN designer hub. Other Pages lines stay.
_DESIGNER_PAGE_LINE = re.compile(r"^- \[[^\]]*\]\(" + re.escape(SITE) + r"/designer/[a-z0-9-]+/\)")


def sync_pages_designers(text):
    """Keep ## Pages designer bullets in designers.json order. Leave every other line."""
    m = _section_match(text, "Pages")
    if not m:
        return text
    lines = m.group(0).split("\n")
    kept = [ln for ln in lines if not _DESIGNER_PAGE_LINE.match(ln)]
    bullets = [f"- [{d['name']}]({SITE}/designer/{d['slug']}/)" for d in DESIGNERS]
    insert_at = next((i for i, ln in enumerate(kept) if ln.startswith("- [") and "繁體中文" in ln), None)
    if insert_at is None:
        insert_at = len(kept)
        while insert_at > 0 and kept[insert_at - 1] == "":
            insert_at -= 1
    new_lines = kept[:insert_at] + bullets + kept[insert_at:]
    return text[:m.start()] + "\n".join(new_lines) + text[m.end():]


def sync_llms_designers(text):
    """Sync ## Designers and the designer links in ## Pages from designers.json."""
    return sync_pages_designers(sync_designers_section(text))


# ---------- feeds ----------
def feed_module():
    spec = importlib.util.spec_from_file_location("bmf", ROOT / "scripts/build-merchant-feed.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_feeds(write: bool):
    mod = feed_module()
    out = {}
    for lang, name in (("en", "google-merchant.xml"), ("zh", "google-merchant-zh.xml")):
        items, _, _ = mod.build_language(PUBLIC, lang)
        out[ROOT / "feeds" / name] = mod.render_feed(items, lang)
    if write:
        for path, text in out.items():
            path.write_text(text, encoding="utf-8")
        mod.assert_feed(ROOT / "feeds/google-merchant.xml", "en")
        mod.assert_feed(ROOT / "feeds/google-merchant-zh.xml", "zh")
    return out


# ---------- build ----------
def build() -> dict[Path, str]:
    files: dict[Path, str] = {}

    def get(path):
        if path not in files:
            files[path] = path.read_text(encoding="utf-8") if path.exists() else ""
        return files[path]

    for d in DESIGNERS:
        for lang, pre in (("en", ""), ("zh", "zh/")):
            files[ROOT / pre / "designer" / d["slug"] / "index.html"] = designer_page(d, lang)
    for path, gid, lst, eager, lang in lists():
        text = set_grid(get(path), gid, lst, lang, eager)
        if gid != "shop-grid":
            text = set_itemlist(text, lst, lang)
        files[path] = text
    by_name = {d["name"]: d for d in DESIGNERS}
    by_brand = {}
    for d in DESIGNERS:
        by_brand.setdefault(d["brandSlug"], []).append(d)
    for lang, pre in (("en", ""), ("zh", "zh/")):
        for path in sorted((ROOT / pre / "item").glob("*/index.html")):
            p = next((x for x in ALL if x["slug"] == path.parent.name), None)
            if p is None or 'name="robots" content="noindex"' in get(path):
                continue
            ds = [by_name[p["designer"]]] if p.get("designer") in by_name else []
            files[path] = add_designer_links(get(path), ds, lang)
        for path in sorted((ROOT / pre / "brand").glob("*/index.html")):
            files[path] = add_designer_links(get(path), by_brand.get(path.parent.name, []), lang)
    files[ROOT / "sitemap.xml"] = build_sitemap(get(ROOT / "sitemap.xml"))
    for name in ("llms.txt", "llms-full.txt"):
        path = ROOT / name
        files[path] = sync_llms_designers(get(path))
    return files


def unlinked(files, feeds) -> list[str]:
    """Every public, non-redirect piece must be reachable from the lists it belongs to."""
    problems = []
    feed_text = {k.name: v for k, v in feeds.items()}
    sm = files[ROOT / "sitemap.xml"]
    brand_pages = {}
    for path in (ROOT / "brand").glob("*/index.html"):
        m = re.search(r'data-filter-brand="([^"]*)"', files.get(path) or path.read_text(encoding="utf-8"))
        brand_pages[html.unescape(m.group(1))] = path.parent.name
    for p in PUBLIC:
        if p["slug"] in REDIRECTS:
            continue
        for lang, pre in (("en", ""), ("zh", "zh/")):
            href = f'href="{item_path(p, lang)}"'
            need = [ROOT / pre / "category" / (p.get("category") or "other") / "index.html"]
            need.append(ROOT / pre / ("sold" if st(p) == "sold" else "shop") / "index.html")
            if p.get("brand") in brand_pages:
                need.append(ROOT / pre / "brand" / brand_pages[p["brand"]] / "index.html")
            d = next((x for x in DESIGNERS if x["name"] == p.get("designer")), None)
            if d:
                need.append(ROOT / pre / "designer" / d["slug"] / "index.html")
            for page in need:
                text = files.get(page) or (page.read_text(encoding="utf-8") if page.exists() else "")
                if href not in text:
                    problems.append(f"{p['slug']}: not linked from /{page.relative_to(ROOT).parent}/")
            if SITE + item_path(p, lang) + "<" not in sm.replace("</loc>", "<"):
                problems.append(f"{p['slug']}: missing from sitemap ({lang})")
        if st(p) in ("available", "pre-order") and p.get("sku"):
            for name, text in feed_text.items():
                if f"<g:id>{p['sku']}</g:id>" not in text:
                    problems.append(f"{p['slug']}: missing from feeds/{name}")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="write nothing; fail if a file is stale or a public piece is unlinked")
    a = ap.parse_args()
    files = build()
    feeds = build_feeds(write=False)
    stale = [p for p, t in {**files, **feeds}.items() if not p.exists() or p.read_text(encoding="utf-8") != t]
    if a.check:   # judge what is on disk now, the files GitHub Pages would serve
        disk_feeds = {k: (k.read_text(encoding="utf-8") if k.exists() else "") for k in feeds}
        problems = unlinked({ROOT / "sitemap.xml": (ROOT / "sitemap.xml").read_text(encoding="utf-8")}, disk_feeds)
        for p in stale:
            print(f"STALE {p.relative_to(ROOT)}")
        for x in problems:
            print(f"UNLINKED {x}")
        if stale or problems:
            sys.exit(1)
        for p in PUBLIC:
            if st(p) in ("available", "pre-order") and not p.get("sku"):
                print(f"NOTE {p['slug']}: no SKU yet, so it stays out of the Merchant feeds until one is set")
        print(f"OK: {len(PUBLIC)} public pieces, every one linked; lists, sitemap, feeds and llms files up to date")
        return
    problems = unlinked(files, feeds)
    if problems:
        for x in problems:
            print(f"UNLINKED {x}")
        sys.exit(1)
    for path, text in files.items():
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            print(f"wrote {path.relative_to(ROOT)}")
    build_feeds(write=True)
    for p in stale:
        if p.parent.name == "feeds":
            print(f"wrote {p.relative_to(ROOT)}")
    hidden = [p["slug"] for p in ALL if not is_public(p)]
    print(f"public {len(PUBLIC)} · not yet public {len(hidden)}{': ' + ', '.join(hidden) if hidden else ''}")


if __name__ == "__main__":
    main()
