/* Tack, tack! site script: product data refresh, shop filters, product page, WhatsApp links.
   Every page is pre-rendered by scripts/build-pages.py (English at /…, 繁中 at /zh/…); this script only
   enhances it: it refreshes grids / stock / buttons if data/products.json changed after the last build,
   runs the shop filters, and fills in the generic /product/?slug= page.
   Product data: /data/products.json. Settings: /assets/js/config.js. UI text: /assets/js/strings.js */
(function () {
  "use strict";
  var C = window.TT_CONFIG, S = window.TT_STRINGS;
  var ZH = /^\/zh(\/|$)/;
  var lang = ZH.test(location.pathname) ? "zh" : "en";   // the language comes from the address: /zh/… is 繁中
  var page = document.body.getAttribute("data-page") || "";
  var DATA = null, PRODUCTS = [], ALL = [];
  var renderers = [];

  function $(s, r) { return (r || document).querySelector(s); }
  function $$(s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); }
  function T() { return S[lang]; }
  function L(o) { return o ? (typeof o === "string" ? o : (o[lang] || o.en || "")) : ""; }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function money(n) { return "HK$" + Number(n || 0).toLocaleString("en-US"); }
  function todayHK() { try { return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Hong_Kong" }).format(new Date()); } catch (e) { return new Date().toISOString().slice(0, 10); } }
  var TODAY = todayHK();
  function daysBetween(a, b) { return Math.round((Date.parse(b) - Date.parse(a)) / 86400000); }
  function slugify(s) { return String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, ""); }
  function hash(s) { var h = 5381; for (var i = 0; i < s.length; i++) h = (h * 33 + s.charCodeAt(i)) >>> 0; return String(h); }

  /* ---------------- language ---------------- */
  function lp(path) { return (lang === "zh" ? "/zh" : "") + path; }
  function withLang(href) {   // an internal link in the current language
    try {
      var u = new URL(href, location.origin);
      if (u.origin !== location.origin || /^\/(assets|data)\//.test(u.pathname) || /\.[a-z0-9]{2,12}$/i.test(u.pathname)) return href;
      return lp(u.pathname.replace(ZH, "/")) + u.search + u.hash;
    } catch (e) { return href; }
  }
  function altUrl() {   // this page in the other language (keeps shop filters)
    var p = location.pathname;
    return (ZH.test(p) ? p.replace(ZH, "/") : "/zh" + p) + location.search + location.hash;
  }

  /* ---------------- WhatsApp ---------------- */
  function wa(text) { return "https://wa.me/" + C.WHATSAPP_NUMBER + (text ? "?text=" + encodeURIComponent(text) : ""); }
  function waStatic() {
    $$("[data-wa]").forEach(function (a) {
      a.href = wa(T().wa.msgGeneral);
      a.target = "_blank"; a.rel = "noopener";
    });
    $$("[data-wa-display]").forEach(function (el) { el.textContent = C.WHATSAPP_DISPLAY; });
  }
  function pageUrl(p) { return C.SITE_URL + lp("/item/" + p.slug + "/"); }
  function waFor(p) {
    var st = state(p).st, w = T().wa, name = L(p.name);
    if (st === "sold") return { href: wa(w.msgSold(name, pageUrl(p))), label: w.askSold };
    if (st === "on-hold") return { href: wa(w.msgHold(name, pageUrl(p))), label: w.askHold };
    return { href: wa(w.msg(name, pageUrl(p))), label: w.ask };
  }
  var WA_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true" fill="currentColor"><path d="M12 2a10 10 0 0 0-8.6 15.1L2 22l5-1.3A10 10 0 1 0 12 2Zm0 18.2a8.2 8.2 0 0 1-4.2-1.1l-.3-.2-3 .8.8-2.9-.2-.3A8.2 8.2 0 1 1 12 20.2Zm4.5-6.1c-.2-.1-1.5-.7-1.7-.8-.2-.1-.4-.1-.6.1l-.8 1c-.1.2-.3.2-.5.1a6.7 6.7 0 0 1-3.3-2.9c-.2-.4.2-.4.7-1.3.1-.2 0-.3 0-.4l-.8-1.8c-.2-.5-.4-.4-.6-.4h-.5a1 1 0 0 0-.7.3 3 3 0 0 0-.9 2.2 5.1 5.1 0 0 0 1.1 2.7 11.7 11.7 0 0 0 4.5 4c1.7.7 2.3.8 3.2.6.5-.1 1.5-.6 1.7-1.2.2-.6.2-1.1.2-1.2-.1-.1-.3-.2-.5-.3Z"/></svg>';
  var SHARE_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12M7 8l5-5 5 5M5 13v6a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6"/></svg>';

  /* ---------------- product helpers (same markup as scripts/build-pages.py) ---------------- */
  function state(p) {
    // Availability is public only as a status: available, on-hold or sold.
    return { st: p.status === "sold" || p.status === "on-hold" ? p.status : "available" };
  }
  // New from the drop (dropDate at DROP_HOUR HKT) until the next weekly drop; no date, no badge. Same as is_new() in build-pages.py.
  function dropStart(p) {
    var day = p.newFrom || p.dropDate;   // newFrom: already live, but the NEW tag waits for a later drop
    if (!day || !/^\d{4}-\d\d-\d\d$/.test(day)) return NaN;
    var h = C.DROP_HOUR == null ? 20 : C.DROP_HOUR;
    return Date.parse(day + "T" + (h < 10 ? "0" : "") + h + ":00:00+08:00");
  }
  function isNew(p, now) {
    var t0 = dropStart(p); if (isNaN(t0)) return false;
    var t = now == null ? Date.now() : now;
    return t >= t0 && t < t0 + (C.NEW_DAYS || 7) * 86400000;
  }
  var MIN_CAT = C.MIN_CATEGORY_PIECES || 2;
  function catLive(c) { return PRODUCTS.filter(function (p) { return (p.category || "other") === c && state(p).st !== "sold"; }).length; }   // same as cat_live()
  function catShown(c) { return catLive(c) >= MIN_CAT; }
  function renderCatLinks() {   // footer category links: hidden until a category has MIN_CATEGORY_PIECES live pieces
    $$("[data-cat-link]").forEach(function (li) { var on = catShown(li.getAttribute("data-cat-link")); if (li.hidden === on) li.hidden = !on; });
  }
  function badges(p) {
    var s = state(p), B = T().badge, out = [];
    if (s.st === "sold") out.push(["sold", B.sold]);
    else if (s.st === "on-hold") out.push(["hold", B.hold]);
    else {
      if (isNew(p)) out.push(["new", B.neu]);
    }
    return '<div class="badges">' + out.map(function (b) { return '<span class="badge badge-' + b[0] + '">' + esc(b[1]) + "</span>"; }).join("") + "</div>";
  }
  function kicker(p) { return [p.brand, p.designer].filter(function (x, i, arr) { return x && arr.indexOf(x) === i; }).join(" · "); }
  function photo(p, i) { return (p.photos && p.photos[i || 0]) || "/assets/brand/mark.svg"; }
  function url(p) { return lp("/item/" + p.slug + "/"); }
  function alt(p) { return isPlaceholder(photo(p)) ? L(p.name) + (lang === "zh" ? "（示意插圖）" : " (illustration)") : (L(p.photoAlt) || L(p.name)); }
  function isPlaceholder(src) { return /placeholder-\d/.test(src); }
  var CARD_SIZES = "(min-width: 1100px) 300px, (min-width: 760px) 31vw, 48vw", GALLERY_SIZES = "(min-width: 900px) 52vw, 100vw";
  function srcset(src, sizes) {   // same as srcset() in build-pages.py
    var m = /^(\/assets\/products\/[^\/]+\/)([^\/]+\.jpg)$/.exec(src || "");
    return m ? ' srcset="' + m[1] + "m/" + m[2] + " 600w, " + src + ' 1200w" sizes="' + sizes + '"' : "";
  }
  function heroPhoto(p) { var ph = p.photos || [], n = p.heroPhoto || 1; return n > 0 && n <= ph.length ? ph[n - 1] : photo(p); }   // same as hero_photo()
  function sizeCm(p) { var d = p.dimensions || {}; return p.category === "lighting" ? (d.dia || d.w || 0) : 0; }   // round shades only, same as size_cm()
  function sizeRow(p, current) {   // same as size_row() in build-pages.py
    var same = PRODUCTS.filter(function (x) { return x.brand === p.brand && x.model && sizeCm(x) && state(x).st !== "sold"; })
      .sort(function (a, b) { return sizeCm(a) - sizeCm(b) || (a.slug < b.slug ? -1 : a.slug > b.slug ? 1 : 0); });
    var uniq = same.map(sizeCm).filter(function (v, i, arr) { return arr.indexOf(v) === i; });
    if (uniq.length < 2) return "";
    var big = Math.max.apply(null, uniq);
    return '<div class="sg-row">' + same.map(function (x) {
      return '<a class="sg-item" href="' + url(x) + '"' + (current && x.slug === current.slug ? ' aria-current="page"' : "") + '><span class="sg-shade" style="width:' + Math.round(100 * sizeCm(x) / big) + '%" aria-hidden="true"></span>' +
        "<strong>" + esc(x.model) + "</strong><span>Ø" + sizeCm(x) + ' cm</span><span class="sg-price">' + money(x.price) + "</span></a>";
    }).join("") + "</div>";
  }
  function pdpTrust(p) {   // same as pdp_trust() in build-pages.py
    var tr = T().trust, g = (p.condition || {}).grade; if (g === "open-box") g = "brand-new";
    var items = (g === "brand-new" ? [tr.neu] : []).concat([tr.genuine, tr.pickup, tr.photos]);
    return '<ul class="pdp-trust">' + items.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ul>";
  }
  function altN(p, i) {   // same as alt_n() in build-pages.py: alt text for photo i
    if (!i) return alt(p);
    var lst = (p.photoAlts && p.photoAlts[lang]) || [];
    return lst[i] || (alt(p) + T().photoMore(i + 1));
  }
  function thumb(src) { return String(src).replace(/^(\/assets\/products\/[^\/]+\/)([^\/]+\.jpg)$/, "$1t/$2"); }   // same as thumb() in build-pages.py
  function notices(keys) {   // same as notices() in build-pages.py
    var N = T().notices; keys = (keys || []).filter(function (k) { return N[k]; });
    return keys.length ? '<ul class="notices">' + keys.map(function (k) { return '<li data-notice="' + esc(k) + '">' + esc(N[k]) + "</li>"; }).join("") + "</ul>" : "";
  }
  function gallery(p, photos) {   // same markup as gallery() in build-pages.py
    var t = T(), n = photos.length;
    if (n === 1) return '<div class="gallery-main"><img id="main-photo" src="' + esc(photos[0]) + '"' + srcset(photos[0], GALLERY_SIZES) + ' alt="' + esc(alt(p)) + '" width="800" height="1000" fetchpriority="high"></div>';
    var slides = photos.map(function (ph, i) {
      return "<img" + (i === 0 ? ' id="main-photo"' : "") + ' src="' + esc(ph) + '"' + srcset(ph, GALLERY_SIZES) + ' alt="' + esc(altN(p, i)) + '" width="800" height="1000"' + (i === 0 ? ' fetchpriority="high"' : ' loading="lazy" decoding="async"') + ">";
    }).join("");
    return '<div class="gallery"><div class="gallery-main gallery-track" id="gallery" tabindex="0" role="region" aria-label="' + esc(t.gallery) + '">' + slides +
      '</div><span class="gallery-count" aria-hidden="true">1 / ' + n + "</span></div>" +
      '<div class="thumbs">' + photos.map(function (ph, i) {
        return '<button type="button" data-slide="' + i + '" aria-current="' + (i === 0) + '" aria-label="' + esc(t.photoN(i + 1, n)) + '"><img src="' + esc(thumb(ph)) + '" alt="" width="80" height="100" decoding="async"></button>';
      }).join("") + "</div>";
  }
  function brandUrl(b) { var info = DATA && DATA.brands && DATA.brands[b]; return lp("/brand/" + ((info && info.slug) || slugify(b)) + "/"); }
  function card(p, eager) {
    var s = state(p);
    return '<article class="card' + (s.st === "sold" ? " is-sold" : "") + '"><a href="' + url(p) + '">' +
      '<div class="card-media"><img src="' + esc(photo(p)) + '"' + srcset(photo(p), CARD_SIZES) + ' alt="' + esc(alt(p)) + '" width="800" height="1000"' + (eager ? "" : ' loading="lazy"') + ' decoding="async">' + badges(p) + "</div>" +
      '<div class="card-body"><p class="card-kicker">' + esc(kicker(p)) + '</p><h3 class="card-title">' + esc(L(p.name)) + "</h3>" + (dims(p) ? '<p class="card-meta">' + esc(dims(p)) + "</p>" : "") +
      '<p class="card-price">' + priceHtml(p) + "</p></div></a></article>";
  }
  /* sig(): a fingerprint of what a grid shows. The build writes the same value into data-sig, so a pre-rendered grid is
     only re-drawn when products.json (or the date, for NEW THIS WEEK) has changed since the last build. */
  // a sold piece shows only "Sold", never its price (same as price_html() in build-pages.py)
  function priceHtml(p) {
    if (state(p).st === "sold") return '<span class="sold-label">' + esc(T().badge.sold) + "</span>";
    return "<span>" + money(p.price) + "</span>" + (p.retailPrice ? '<span class="retail">' + esc(T().retail(money(p.retailPrice))) + "</span>" : "");
  }
  // condition: grade chip, open-box note, condition notes, final-sale line (same as build-pages.py)
  var COND_NOTE_KEYS = ["flaws", "parts", "box", "electrics", "mark", "year"];
  function gradeOf(p) { var g = (p.condition || {}).grade || ""; return g === "open-box" ? "brand-new" : g; }
  function openBox(p) { var c = p.condition || {}; return gradeOf(p) === "brand-new" && (!!c.openBox || c.grade === "open-box"); }
  function gradeLabel(p) { var g = gradeOf(p), t = T(); if (!t.grades[g]) return ""; return openBox(p) ? t.openBox[0] : t.grades[g][0]; }
  function gradeChip(p) { var l = gradeLabel(p); return l && state(p).st !== "sold" ? '<a class="grade-chip" href="' + lp("/faq/") + '#condition-guide" aria-label="' + esc(T().chipAria(l)) + '">' + esc(l) + "</a>" : ""; }
  function condNotes(p) {
    var c = p.condition || {}, lab = T().condNotes;
    var rows = COND_NOTE_KEYS.filter(function (k) { return L(c[k]); });
    return rows.length ? '<h3 class="cond-notes-h">' + esc(lab.title) + '</h3><dl class="specs cond-notes">' + rows.map(function (k) { return "<dt>" + esc(lab[k]) + "</dt><dd>" + esc(L(c[k])) + "</dd>"; }).join("") + "</dl>" : "";
  }
  function finalNote(p) { var g = gradeOf(p); return g && g !== "brand-new" ? '<p class="final-note">' + esc(T().finalNote) + "</p>" : ""; }
  function sig(list) {
    return hash(list.map(function (p) { var s = state(p); var sold = s.st === "sold"; return [p.slug, s.st, isNew(p) ? 1 : 0, sold ? 0 : p.price || 0, p.retailPrice && !sold ? p.retailPrice : "", L(p.name), photo(p)].join(":"); }).join("|"));
  }
  function grid(el, list, eager) {
    if (!el) return;
    var s = sig(list);
    if (el.getAttribute("data-sig") === s) return;
    el.innerHTML = list.map(function (p, i) { return card(p, eager && i < 4); }).join("");
    el.setAttribute("data-sig", s);
  }
  function setHTML(el, h) { if (el && el.innerHTML !== h) el.innerHTML = h; }
  function byNewest(a, b) { return (b.dropDate || "").localeCompare(a.dropDate || "") || (b.featured ? 1 : 0) - (a.featured ? 1 : 0); }
  function soldLast(a, b) { return (state(a).st === "sold" ? 1 : 0) - (state(b).st === "sold" ? 1 : 0) || byNewest(a, b); }

  /* ---------------- data ---------------- */
  function load() {
    return fetch("/data/products.json", { cache: "no-cache" }).then(function (r) { return r.json(); }).then(function (d) {
      DATA = d;
      ALL = (d.products || []).filter(function (p) { return p.published !== false && p.slug; });
      PRODUCTS = ALL.filter(function (p) { return !p.dropDate || p.dropDate <= TODAY; }); // future drop dates stay hidden until the day
    });
  }
  function rerender() { renderers.forEach(function (fn) { try { fn(); } catch (e) { console.error(e); } }); }

  /* ---------------- home ---------------- */
  function renderHome() {
    var active = PRODUCTS.filter(function (p) { return state(p).st !== "sold"; });
    var drop = active.filter(function (p) { return isNew(p); }).sort(function (a, b) { return (b.featured ? 1 : 0) - (a.featured ? 1 : 0) || byNewest(a, b); });
    var dh = $("#drop-h"), dtx = T().dropH[drop.length ? "neu" : "latest"]; if (dh && dh.textContent !== dtx) dh.textContent = dtx;
    if (!drop.length) drop = active.slice().sort(byNewest);
    grid($("#drop-grid"), drop.slice(0, 8), true);
    // #drop-date is fixed text ("New pieces every Thursday"), pre-rendered per language: nothing to update here

    $$("[data-cat-count]").forEach(function (el) {
      var k = el.getAttribute("data-cat-count"), n = active.filter(function (p) { return p.category === k; }).length;
      var txt = T().pieces(n);
      if (el.textContent !== txt) el.textContent = txt;
      var tile = el.closest(".cat"), on = n >= MIN_CAT; if (tile && tile.hidden === on) tile.hidden = !on;   // empty categories stay hidden until they fill up
    });
    var cs = $("#cat-section"); if (cs) { var anyCat = $$("[data-cat-count]").some(function (el) { return !el.closest(".cat").hidden; }); if (cs.hidden === anyCat) cs.hidden = !anyCat; }
    var sg = $("#size-section"), sp = active.filter(function (p) { return sizeRow(p); })[0];   // AKARI size guide: shows by itself once the lamps are live
    if (sg) {
      if (sp) { setHTML($("#size-guide"), sizeRow(sp)); var sh = $("#size-guide-h"), stx = T().sizeTitle(sp.brand || ""); if (sh && sh.textContent !== stx) sh.textContent = stx; }
      if (sg.hidden === !!sp) sg.hidden = !sp;
    }

    var brands = {};
    PRODUCTS.forEach(function (p) { var k = p.brand; if (!brands[k]) brands[k] = { brand: k, designers: [], n: 0 }; brands[k].n++; if (p.designer && brands[k].designers.indexOf(p.designer) < 0) brands[k].designers.push(p.designer); });
    setHTML($("#brand-row"), Object.keys(brands).sort().map(function (k) {
      var b = brands[k];
      return '<a class="brand-pill" href="' + brandUrl(k) + '"><strong>' + esc(k) + "</strong><span>" + esc(b.designers.join(", ") || T().pieces(b.n)) + "</span></a>";
    }).join(""));

    var sold = PRODUCTS.filter(function (p) { return state(p).st === "sold"; }).sort(byNewest);
    var ss = $("#sold-section"); if (ss) { ss.hidden = !sold.length; grid($("#sold-grid"), sold.slice(0, 4)); }

    var feat = PRODUCTS.filter(function (p) { return p.featured && state(p).st !== "sold"; });
    var a = feat[0] || active[0], b = feat.filter(function (p) { return p.brand !== (a && a.brand); })[0] || feat[1] || active[1];
    [["#shot-a", a], ["#shot-b", b]].forEach(function (x) {
      var el = $(x[0]), p = x[1]; if (!el || !p) return;
      var link = $("a", el), img = $("img", el);
      var hp = heroPhoto(p), hi = (p.photos || []).indexOf(hp);
      if (link && img && link.getAttribute("href") === url(p) && img.getAttribute("src") === hp) return;   // pre-rendered and still right
      el.innerHTML = '<a href="' + url(p) + '"><img src="' + esc(hp) + '"' + srcset(hp, "(min-width: 900px) 30vw, 62vw") + ' alt="' + esc(altN(p, hi > 0 ? hi : 0)) + '" width="800" height="1000" fetchpriority="high"></a>';
    });
    var tag = $("#hero-tag");
    if (tag && a) { if (tag.getAttribute("href") !== url(a)) tag.setAttribute("href", url(a)); setHTML(tag, '<span class="dot"></span>' + (isNew(a) ? esc(T().badge.neu) + " · " : "") + esc(L(a.name))); }

    var ig = $("#ig-grid");
    if (ig) {
      var pics = PRODUCTS.slice().sort(byNewest).slice(0, 6);
      setHTML(ig, pics.map(function (p) { return '<a href="https://www.instagram.com/' + C.INSTAGRAM + '/" target="_blank" rel="noopener" aria-label="Instagram @' + C.INSTAGRAM + ": " + esc(L(p.name)) + '"><img src="' + esc(photo(p)) + '" alt="" loading="lazy" width="800" height="1000"></a>'; }).join(""));
    }
  }

  /* ---------------- shop ---------------- */
  var PRICE = { u500: [0, 499.99], "500-1500": [500, 1500], "1500-5000": [1500.01, 5000], o5000: [5000.01, 1e12] };
  function readFilters() {
    var q = new URLSearchParams(location.search);
    return { category: q.get("category") || "", brand: q.get("brand") || "", status: q.get("status") || "active", price: q.get("price") || "any", sort: q.get("sort") || "newest" };
  }
  function writeFilters(f) {
    var q = new URLSearchParams(location.search);
    [["category", ""], ["brand", ""], ["status", "active"], ["price", "any"], ["sort", "newest"]].forEach(function (d) { if (f[d[0]] && f[d[0]] !== d[1]) q.set(d[0], f[d[0]]); else q.delete(d[0]); });
    var s = q.toString(); history.replaceState(null, "", location.pathname + (s ? "?" + s : ""));
  }
  function applyFilters(list, f) {
    return list.filter(function (p) {
      var st = state(p).st;
      if (f.category && p.category !== f.category) return false;
      if (f.brand && p.brand !== f.brand && p.designer !== f.brand) return false;
      if (f.status === "active" && st === "sold") return false;
      if (f.status !== "active" && f.status !== "all" && st !== f.status) return false;
      if (PRICE[f.price] && (p.price < PRICE[f.price][0] || p.price > PRICE[f.price][1])) return false;
      return true;
    }).sort(function (a, b) {
      if (f.sort === "price-asc") return a.price - b.price;
      if (f.sort === "price-desc") return b.price - a.price;
      if (f.sort === "brand") return (a.brand + L(a.name)).localeCompare(b.brand + L(b.name));
      return soldLast(a, b);
    });
  }
  function options(sel, pairs, value) {
    var have = Array.prototype.map.call(sel.options, function (o) { return o.value + "\u0001" + o.text; }).join("\u0002");
    if (have !== pairs.map(function (p) { return p[0] + "\u0001" + p[1]; }).join("\u0002"))
      sel.innerHTML = pairs.map(function (p) { return '<option value="' + esc(p[0]) + '"' + (p[0] === value ? " selected" : "") + ">" + esc(p[1]) + "</option>"; }).join("");
    if (sel.value !== value) sel.value = value;
  }
  function renderShop() {
    var f = readFilters(), t = T();
    var cats = ["lighting", "seating", "sofas", "storage", "tables", "decor"];
    var counts = {}; PRODUCTS.forEach(function (p) { if (state(p).st !== "sold") counts[p.category] = (counts[p.category] || 0) + 1; });
    setHTML($("#cat-chips"), [["", t.all]].concat(cats.filter(function (c) { return (counts[c] || 0) >= MIN_CAT || c === f.category; }).map(function (c) { return [c, t.cat[c]]; })).map(function (c) {
      var n = c[0] ? counts[c[0]] || 0 : PRODUCTS.filter(function (p) { return state(p).st !== "sold"; }).length;
      return '<button type="button" class="chip-btn" data-cat="' + c[0] + '" aria-pressed="' + (f.category === c[0]) + '">' + esc(c[1]) + '<span class="n">' + n + "</span></button>";
    }).join(""));
    var names = {}; PRODUCTS.forEach(function (p) { names[p.brand] = 1; if (p.designer) names[p.designer] = 1; });
    options($("#f-brand"), [["", t.all]].concat(Object.keys(names).sort().map(function (n) { return [n, n]; })), f.brand);
    options($("#f-status"), ["active", "available", "on-hold", "sold", "all"].map(function (k) { return [k, t.status[k]]; }), f.status);
    options($("#f-price"), ["any", "u500", "500-1500", "1500-5000", "o5000"].map(function (k) { return [k, t.price[k]]; }), f.price);
    options($("#f-sort"), ["newest", "price-asc", "price-desc", "brand"].map(function (k) { return [k, t.sort[k]]; }), f.sort);
    var list = applyFilters(PRODUCTS, f);
    var rc = $("#result-count"), rtx = t.results(list.length); if (rc.textContent !== rtx) rc.textContent = rtx;
    var dirty = f.category || f.brand || f.status !== "active" || f.price !== "any";
    $("#reset").hidden = !dirty;
    var g = $("#shop-grid");
    if (list.length) grid(g, list, true);
    else { g.innerHTML = '<div class="empty"><h3>' + esc(t.noResults) + "</h3><p>" + esc(t.noResultsCta) + '</p><a class="btn btn-sm" href="' + wa(t.wa.msgGeneral) + '" target="_blank" rel="noopener">' + WA_ICON + esc(t.wa.general) + "</a></div>"; g.removeAttribute("data-sig"); }
    var h = $("#shop-title-cat"); if (h) h.textContent = f.category ? t.cat[f.category] : "";
  }
  function bindShop() {
    document.addEventListener("click", function (e) {
      var c = e.target.closest("[data-cat]"); if (c) { var f = readFilters(); f.category = c.getAttribute("data-cat"); writeFilters(f); renderShop(); }
      if (e.target.closest("#reset")) { writeFilters({ category: "", brand: "", status: "active", price: "any", sort: readFilters().sort }); renderShop(); }
    });
    ["brand", "status", "price", "sort"].forEach(function (k) {
      $("#f-" + k).addEventListener("change", function (e) { var f = readFilters(); f[k] = e.target.value; writeFilters(f); renderShop(); });
    });
  }

  /* ---------------- sold archive ---------------- */
  function renderSold() {
    var sold = PRODUCTS.filter(function (p) { return state(p).st === "sold"; }).sort(byNewest);
    var g = $("#sold-grid"); if (!g) return;
    if (sold.length) return grid(g, sold);
    var s = sig(sold); if (g.getAttribute("data-sig") === s) return;
    g.innerHTML = '<div class="empty"><h3>' + esc(T().soldEmpty) + '</h3><p><a class="text-link" href="' + lp("/shop/") + '">' + esc(T().shopAll) + " →</a></p></div>";
    g.setAttribute("data-sig", s);
  }

  /* ---------------- brand & category pages ---------------- */
  function renderList() {
    var g = $("#list-grid"); if (!g) return;
    var b = g.getAttribute("data-filter-brand"), c = g.getAttribute("data-filter-category");
    grid(g, PRODUCTS.filter(function (p) { return b ? p.brand === b : (p.category || "other") === c; }).sort(soldLast), true);
  }

  /* ---------------- product ---------------- */
  function findProduct() {
    var q = new URLSearchParams(location.search), slug = document.body.getAttribute("data-slug") || q.get("slug");
    return ALL.filter(function (p) { return slug && p.slug === slug; })[0] ||
      ALL.filter(function (p) { return slug && (p.oldSlugs || []).indexOf(slug) >= 0; })[0];   // renamed items: old links still work
  }
  function dims(p) {
    var d = p.dimensions || {}, parts = [];
    if (d.dia) parts.push("Ø" + d.dia);
    if (d.w) parts.push("W " + d.w); if (d.d) parts.push("D " + d.d); if (d.h) parts.push("H " + d.h);
    return parts.length ? parts.join(" × ") + " " + (d.unit || "cm") : "";
  }
  function policyText(p) {
    var t = T().policy, price = +p.price || 0;
    if (state(p).st === "sold") return t.sold;
    if (price < 1500) return t.full(money(price));
    if (price < 10000) return t.dep30(money(Math.ceil(price * 0.3)), money(price));
    return t.dep20(money(Math.max(3000, Math.ceil(price * 0.2))), money(price));
  }
  function related(p) {
    var same = PRODUCTS.filter(function (x) { return x.slug !== p.slug && (x.brand === p.brand || x.designer === p.designer) && state(x).st !== "sold"; });
    var more = same.concat(PRODUCTS.filter(function (x) { return x.slug !== p.slug && same.indexOf(x) < 0 && state(x).st !== "sold"; })).slice(0, 4);
    return { same: same, more: more };
  }
  function productMarkup(p) {   // same markup as product_markup() in scripts/build-pages.py
    var t = T(), s = state(p), cta = waFor(p), name = L(p.name);
    var grade = (p.condition || {}).grade; if (grade === "open-box") grade = "brand-new";   // old grade merged into Brand new
    var G = t.grades, gkeys = Object.keys(G), gi = gkeys.indexOf(grade);
    var stockLine = t.stock[s.st === "sold" ? "sold" : s.st === "on-hold" ? "onHold" : "available"];
    var specs = [
      [t.labels.designer, p.designer], [t.labels.brand, p.brand, p.brand ? brandUrl(p.brand) : ""], [t.labels.model, p.model], [t.labels.year, L(p.year)],
      [t.labels.colour, L(p.colour)], [t.labels.material, L(p.material)], [t.labels.dims, dims(p) || t.dimsTbc],
      [t.labels.weight, p.dimensions && p.dimensions.weightKg ? "≈ " + p.dimensions.weightKg + " kg" : ""]
    ].filter(function (r) { return r[1]; });
    var photos = (p.photos && p.photos.length ? p.photos : [photo(p)]);
    var story = DATA.stories && DATA.stories[p.storyKey || ""];
    var notes = L((p.condition || {}).notes);
    var details = (p.details && (p.details[lang] || p.details.en)) || [];
    var cat = p.category || "other", sep = '<span aria-hidden="true">/</span>', rel = related(p);
    return '<nav class="crumbs" aria-label="' + esc(t.crumbs) + '"><a href="' + lp("/") + '">' + esc(t.home) + "</a>" + sep +
      '<a href="' + lp("/shop/") + '">' + esc(t.shop) + "</a>" + sep + '<a href="' + lp("/category/" + cat + "/") + '">' + esc(t.cat[cat] || "") + "</a>" + sep +
      '<span aria-current="page">' + esc(name) + "</span></nav>" +
      '<div class="pdp">' +
        '<div class="pdp-gallery">' + gallery(p, photos) +
          (photos.some(isPlaceholder) ? '<p class="photo-note">' + esc(t.photoNote) + "</p>" : "") +
        "</div>" +
        '<div class="pdp-info">' +
          '<p class="eyebrow">' + esc(kicker(p)) + "</p>" + badges(p) +
          "<h1>" + esc(name) + "</h1>" +
          '<div class="pdp-price">' + priceHtml(p) + gradeChip(p) + "</div>" +
          '<p class="pdp-stock">' + esc(stockLine) + "</p>" +
          '<p class="pdp-lede">' + esc(L(p.description)) + "</p>" +
          notices(p.notices) +
          '<div class="cta-row" id="main-cta"><a class="btn" href="' + cta.href + '" target="_blank" rel="noopener">' + WA_ICON + esc(cta.label) + '</a><button type="button" class="btn btn-ghost share-btn" id="share" aria-label="' + esc(t.share) + '">' + SHARE_ICON + "</button></div>" +
          finalNote(p) + pdpTrust(p) +
          '<p class="fine">' + esc(t.policy.pay) + "</p>" +
          '<section class="block"><h2>' + esc(t.labels.condition) + '</h2><div class="grade-row"><span>' + esc(gi >= 0 ? gradeLabel(p) : t.gradeTbc) + '</span><span class="tip"><button type="button" class="tip-btn" aria-expanded="false" aria-controls="grade-pop" aria-label="' + esc(t.gradeHelp) + '">?</button>' +
            '<span class="tip-pop" id="grade-pop" role="tooltip" hidden><strong>' + esc(t.scaleTitle) + "</strong><ol>" + gkeys.map(function (k, i) { return '<li class="' + (i === gi ? "on" : "") + '"><b>' + esc(G[k][0]) + "</b>: " + esc(G[k][1]) + "</li>"; }).join("") + "</ol></span></span></div>" +
            '<ol class="scale" aria-hidden="true">' + gkeys.map(function (k, i) { return '<li class="' + (i === gi ? "on" : "") + '"></li>'; }).join("") + '</ol><div class="scale-labels" aria-hidden="true"><span>' + esc(G[gkeys[0]][0]) + "</span><span>" + esc(G[gkeys[gkeys.length - 1]][0]) + "</span></div>" +
            '<p class="fine" style="margin-top:10px">' + esc(gi >= 0 ? (notes || (openBox(p) ? t.openBox[1] : G[grade][1])) : t.gradeTbcNote) + "</p>" + condNotes(p) + "</section>" +
          '<section class="block"><h2>' + esc(t.labels.specs) + '</h2><dl class="specs">' + specs.map(function (r) { return "<dt>" + esc(r[0]) + "</dt><dd>" + (r[2] ? '<a href="' + r[2] + '">' + esc(r[1]) + "</a>" : esc(r[1])) + "</dd>"; }).join("") + "</dl></section>" +
          (details.length ? '<section class="block"><h2>' + esc(t.labels.details) + '</h2><ul class="ticks">' + details.map(function (d) { return "<li>" + esc(d) + "</li>"; }).join("") + "</ul></section>" : "") +
          (sizeRow(p, p) ? '<section class="block size-block"><h2>' + esc(t.sizeTitle(p.brand || "")) + "</h2>" + sizeRow(p, p) + '<p class="fine">' + esc(t.sizeNote) + "</p></section>" : "") +
          '<section class="block"><h2>' + esc(t.labels.fulfilment) + "</h2><p>" + esc(t.fulfil[p.fulfilment] || t.fulfil.both) + ' <a href="' + lp("/delivery/") + '">' + esc(t.fulfilMore) + '</a></p><p class="install-note">' + esc(t.install) + "</p></section>" +
          '<section class="block"><h2>' + esc(t.labels.policy) + '</h2><p id="policy-text">' + esc(policyText(p)) + '</p><p><a class="text-link" href="' + lp("/how-to-buy/") + '">' + esc(t.policy.more) + " →</a></p></section>" +
        "</div>" +
      "</div>" +
      (story ? '<section class="section-tight"><div class="story"><div><p class="eyebrow">' + esc(t.labels.story) + "</p><h2>" + esc(L(story.title)) + "</h2></div><p>" + esc(L(story.body)) + "</p></div></section>" : "") +
      '<section class="section-tight" id="more"><div class="section-head"><h2>' + esc(rel.same.length >= 4 ? t.more(p.brand || "") : t.alsoLike) + '</h2><a class="text-link" href="' + lp("/shop/") + '">' + esc(t.shopAll) + ' →</a></div><div class="grid grid-4">' + rel.more.map(function (x) { return card(x); }).join("") + "</div></section>" +
      '<div class="sticky-cta" id="sticky-cta"><div class="p">' + (s.st === "sold" ? esc(t.badge.sold) : money(p.price)) + "<small>" + esc(name) + '</small></div><a class="btn" href="' + cta.href + '" target="_blank" rel="noopener">' + WA_ICON + "WhatsApp</a></div>";
  }
  var LIVE_PARTS = [".pdp-info > .badges", ".pdp-price", ".pdp-stock", "#main-cta", "#policy-text", "#more", "#sticky-cta"];
  function renderProduct() {
    var root = $("#product-root"); if (!root) return;
    var p = findProduct(), t = T();
    if (!p) {
      if (root.hasAttribute("data-static")) return;   // a pre-rendered page keeps its content
      root.innerHTML = '<div class="empty" style="margin:40px 0"><h3>' + esc(t.notFound) + '</h3><p><a class="text-link" href="' + lp("/shop/") + '">' + esc(t.shopAll) + " →</a></p></div>";
      return;
    }
    var markup = productMarkup(p);
    if (root.hasAttribute("data-static")) {
      // Pre-rendered page: only swap the parts that depend on live stock / price, and only if they changed.
      var fresh = document.createElement("div"); fresh.innerHTML = markup;
      LIVE_PARTS.forEach(function (sel) {
        var a = $(sel, root), b = $(sel, fresh);
        if (a && b && a.outerHTML !== b.outerHTML) a.parentNode.replaceChild(b, a);
      });
    } else {
      root.innerHTML = markup;
      document.title = L(p.name) + " | " + C.BRAND;
    }
    document.body.classList.add("has-sticky");
    if (!window.__ttSticky) { window.__ttSticky = true; window.addEventListener("scroll", function () { var s = $("#sticky-cta"), m = $("#main-cta"); if (s && m) s.classList.toggle("show", m.getBoundingClientRect().bottom < 0); }, { passive: true }); }
    var sticky = $("#sticky-cta"), main = $("#main-cta");
    if (sticky && main) sticky.classList.toggle("show", main.getBoundingClientRect().bottom < 0);
  }
  function gallerySync(i) {   // highlight thumbnail i and update the "2 / 3" counter
    $$("[data-slide]").forEach(function (b) { b.setAttribute("aria-current", String(Number(b.getAttribute("data-slide")) === i)); });
    var c = $(".gallery-count"); if (c) c.textContent = (i + 1) + " / " + $$("[data-slide]").length;
  }
  function bindProduct() {
    var galleryTimer;
    document.addEventListener("scroll", function (e) {   // swipe on the photo track (scroll events don't bubble, so listen in the capture phase)
      var track = e.target; if (!track || track.id !== "gallery") return;
      clearTimeout(galleryTimer);
      galleryTimer = setTimeout(function () { gallerySync(Math.round(track.scrollLeft / Math.max(1, track.clientWidth))); }, 60);
    }, true);

    document.addEventListener("click", function (e) {
      var th = e.target.closest("[data-slide]"), track = $("#gallery");
      if (th && track) {
        var still = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
        track.scrollTo({ left: Number(th.getAttribute("data-slide")) * track.clientWidth, behavior: still ? "auto" : "smooth" });
        gallerySync(Number(th.getAttribute("data-slide")));
      }
      var tip = e.target.closest(".tip-btn"), pop = $("#grade-pop");
      if (tip && pop) { var open = pop.hidden; pop.hidden = !open; tip.setAttribute("aria-expanded", open); }
      else if (pop && !e.target.closest(".tip-pop")) { pop.hidden = true; var b = $(".tip-btn"); if (b) b.setAttribute("aria-expanded", "false"); }
      if (e.target.closest("#share")) {
        var p = findProduct(), link = p ? pageUrl(p) : location.href;
        if (navigator.share) navigator.share({ title: document.title, url: link }).catch(function () {});
        else if (navigator.clipboard) navigator.clipboard.writeText(link).then(function () { toast(T().copied); }, function () { prompt("", link); });
        else prompt("", link);
      }
    });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") { var pop = $("#grade-pop"); if (pop) pop.hidden = true; } });
  }
  function toast(msg) { var el = document.createElement("div"); el.className = "toast"; el.setAttribute("role", "status"); el.textContent = msg; document.body.appendChild(el); setTimeout(function () { el.remove(); }, 1800); }

  /* ---------------- chrome ---------------- */
  function chrome() {
    // Language switch: a plain link to the other language's page. Remember the choice and keep filters / #anchors.
    $$("[data-lang-toggle]").forEach(function (a) {
      if (page === "404" || location.search || location.hash || !a.getAttribute("href") || a.getAttribute("href") === "{{alt_url}}") a.setAttribute("href", altUrl());
      a.addEventListener("click", function () {
        try { localStorage.setItem("tt-lang", lang === "zh" ? "en" : "zh"); } catch (e) {}
        a.setAttribute("href", altUrl());   // shop filters may have changed since the page loaded
      });
    });
    var mb = $(".menu-btn"), mn = $("#mobile-nav");
    if (mb && mn) mb.addEventListener("click", function () { var o = mn.hidden; mn.hidden = !o; mb.setAttribute("aria-expanded", o); });
    var here = location.pathname.replace(/index\.html$/, "").replace(ZH, "/");
    $$(".nav a, .mobile-nav a, .side-nav a").forEach(function (a) {
      var p = new URL(a.getAttribute("href"), location.origin).pathname.replace(ZH, "/");
      if (p !== "/" && (here === p || (p === "/shop/" && /^\/(item|brand|category)\//.test(here)))) a.setAttribute("aria-current", "page");
    });
    var hd = $(".site-header"); if (hd) { var on = function () { hd.classList.toggle("scrolled", window.scrollY > 8); }; window.addEventListener("scroll", on, { passive: true }); on(); }
    var y = $("#year"); if (y) y.textContent = new Date().getFullYear();
    if (page === "404") {   // the one bilingual page: GitHub Pages serves it for every missing address
      if (lang === "zh") { var tz = $('meta[name="tt:title-zh"]'); if (tz) document.title = tz.content; }
      $$('a[href^="/"]').forEach(function (a) { if (!a.hasAttribute("data-lang-toggle")) a.setAttribute("href", withLang(a.getAttribute("href"))); });
    }
    waStatic();
  }

  chrome();
  var needs = { home: renderHome, shop: renderShop, sold: renderSold, product: renderProduct, list: renderList };
  if (needs[page] || $("[data-cat-link]")) {
    if (page === "shop") bindShop();
    if (page === "product") bindProduct();
    if (needs[page]) renderers.push(needs[page]);
    renderers.push(renderCatLinks);
    load().then(rerender).catch(function (e) { console.error("Could not load products", e); });
  }
  window.TT = { wa: wa, lang: lang, sig: sig, hash: hash, isNew: isNew };
})();
