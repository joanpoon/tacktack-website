/* Interface text in English and Traditional Chinese (Hong Kong).
   Page copy lives in the HTML files (look for class="l-en" / class="l-zh"). */
window.TT_STRINGS = {
  en: {
    cat: { lighting: "Lighting", seating: "Seating", sofas: "Sofas & Lounge", storage: "Storage", tables: "Tables", decor: "Decor & Objects", other: "Other" },
    all: "All",
    pieces: n => n === 1 ? "1 piece" : n + " pieces",
    comingSoon: "Coming soon",
    badge: { hold: "On hold", sold: "Sold", neu: "New this week" },
    grades: {
      "brand-new": ["Brand new", "Unused and never installed."],
      "near-mint": ["Near mint", "Lightly used, with no marks you'd notice at a normal distance."],
      "excellent": ["Excellent", "Small signs of use you'd only see up close. Works perfectly."],
      "good": ["Good", "Visible wear consistent with age, such as small marks or light scratches. Works as it should."],
      "fair": ["Fair", "Noticeable wear or cosmetic flaws, priced to match. Details in the notes."]
    },
    gradeTbc: "Grade to be confirmed",
    gradeTbcNote: "We're grading this piece now. WhatsApp us for close-up photos in the meantime.",
    scaleTitle: "Our 5-step condition scale",
    gradeHelp: "What do the grades mean?",
    labels: { designer: "Designer", brand: "Brand", model: "Model", year: "Year", colour: "Colour", material: "Material", dims: "Dimensions", weight: "Weight", sku: "SKU", condition: "Condition", details: "Good to know", fulfilment: "Pickup & delivery", policy: "Reserving & paying", story: "The story", specs: "Details" },
    dimsTbc: "Measurements coming soon, ask us",
    stock: { available: "Available now", onHold: "On hold right now", sold: "This piece has found its home" },
    retail: p => "New retail approx. " + p,
    fulfil: {
      pickup: "Self-pickup by appointment. We share the address when you book.",
      delivery: "Delivery across Hong Kong, quoted over WhatsApp.",
      both: "Self-pickup by appointment, or delivery across Hong Kong quoted over WhatsApp. Small pieces can go by courier."
    },
    policy: {
      full: p => "Under HK$1,500: reserve by paying in full (" + p + "). Pick up or arrange delivery within 7 days.",
      dep30: (d, p) => "30% deposit (" + d + ") holds it for up to 7 days. Balance before pickup or delivery.",
      dep20: (d, p) => "20% deposit (" + d + ") holds it for up to 14 days. Balance before pickup or delivery.",
      pay: "FPS · PayMe · Bank transfer. Messages and likes don't hold items: first paid, first served.",
      more: "Full holds & deposits policy"
    },
    wa: {
      ask: "WhatsApp to reserve",
      askHold: "Join the waitlist",
      askSold: "Ask about similar pieces",
      general: "Chat on WhatsApp",
      msg: (name, sku, url) => "Hi Tack, tack! I'm interested in " + name + " (SKU " + sku + "). Is it still available?\n" + url,
      msgHold: (name, sku, url) => "Hi Tack, tack! " + name + " (SKU " + sku + ") shows as on hold. Could you let me know if it becomes available?\n" + url,
      msgSold: (name, sku, url) => "Hi Tack, tack! I saw " + name + " (SKU " + sku + ") in your sold archive. Please let me know if you find another one.\n" + url,
      msgGeneral: "Hi Tack, tack! I have a question:"
    },
    share: "Share", copied: "Link copied",
    more: b => "More from " + b,
    alsoLike: "You might also like",
    shopAll: "Shop all",
    home: "Home", shop: "Shop", crumbs: "Breadcrumb", fulfilMore: "Delivery & pickup details",
    filters: { category: "Category", brand: "Brand / designer", status: "Availability", price: "Price", sort: "Sort", reset: "Clear filters" },
    status: { active: "Available & on hold", available: "Available now", "on-hold": "On hold", sold: "Sold", all: "Everything" },
    price: { any: "Any price", u500: "Under HK$500", "500-1500": "HK$500–1,500", "1500-5000": "HK$1,500–5,000", o5000: "HK$5,000+" },
    sort: { newest: "Newest", "price-asc": "Price: low to high", "price-desc": "Price: high to low", brand: "Brand A–Z" },
    results: n => n === 1 ? "1 piece" : n + " pieces",
    noResults: "Nothing matches those filters right now.",
    noResultsCta: "Hunting for something specific? Tell us on WhatsApp and we'll keep an eye out.",
    soldEmpty: "Nothing in the archive yet: every piece is still looking for its home.",
    photoNote: "Illustration only. Real photos are coming soon; WhatsApp us and we'll send some today.",
    notFound: "We couldn't find that piece. It may have been renamed or removed.",
    dropTitle: d => "Fresh Thursday · " + d,
    by: "by", for_: "for"
  },
  zh: {
    cat: { lighting: "燈飾", seating: "座椅", sofas: "梳化", storage: "收納", tables: "枱", decor: "擺設及家品", other: "其他" },
    all: "全部",
    pieces: n => n + " 件",
    comingSoon: "即將上架",
    badge: { hold: "已留貨", sold: "已售出", neu: "本週新貨" },
    grades: {
      "brand-new": ["全新", "未經使用，從未安裝。"],
      "near-mint": ["近乎全新", "輕度使用，正常距離下看不到痕跡。"],
      "excellent": ["極佳", "只有近看才見的輕微使用痕跡，功能完好。"],
      "good": ["良好", "有與年份相符的使用痕跡，例如小花痕或輕微刮痕，功能正常。"],
      "fair": ["一般", "有較明顯的磨損或外觀瑕疵，價錢已反映，詳情見備註。"]
    },
    gradeTbc: "品相評級稍後更新",
    gradeTbcNote: "我們正在為這件貨品評級，歡迎 WhatsApp 索取近照。",
    scaleTitle: "五級品相評級",
    gradeHelp: "評級代表甚麼？",
    labels: { designer: "設計師", brand: "品牌", model: "型號", year: "年份", colour: "顏色", material: "物料", dims: "尺寸", weight: "重量", sku: "貨號", condition: "品相", details: "小提示", fulfilment: "自取及送貨", policy: "留貨及付款", story: "設計故事", specs: "規格" },
    dimsTbc: "尺寸稍後更新，歡迎查詢",
    stock: { available: "現貨供應", onHold: "目前已被留貨", sold: "這件已經搵到新主人" },
    retail: p => "全新參考價約 " + p,
    fulfil: {
      pickup: "預約自取，確認後會提供地址。",
      delivery: "全港送貨，運費經 WhatsApp 報價。",
      both: "可預約自取，或全港送貨（運費經 WhatsApp 報價）。細件貨品可安排速遞。"
    },
    policy: {
      full: p => "HK$1,500 以下貨品須全數付款（" + p + "）方可確認，並於 7 天內自取或安排送貨。",
      dep30: (d, p) => "付 30% 訂金（" + d + "）可留貨最多 7 天，餘款須於自取或送貨前付清。",
      dep20: (d, p) => "付 20% 訂金（" + d + "）可留貨最多 14 天，餘款須於自取或送貨前付清。",
      pay: "接受 FPS 轉數快、PayMe 及銀行轉帳。私訊及讚好不代表留貨，先付先得。",
      more: "查看完整留貨及訂金安排"
    },
    wa: {
      ask: "WhatsApp 查詢／留貨",
      askHold: "加入候補名單",
      askSold: "查詢同類貨品",
      general: "WhatsApp 聯絡我們",
      msg: (name, sku, url) => "你好 Tack, tack!，我想查詢「" + name + "」（貨號 " + sku + "），請問仲有貨嗎？\n" + url,
      msgHold: (name, sku, url) => "你好 Tack, tack!，「" + name + "」（貨號 " + sku + "）顯示已留貨，如果重新有貨可以通知我嗎？\n" + url,
      msgSold: (name, sku, url) => "你好 Tack, tack!，我喺已售出區見到「" + name + "」（貨號 " + sku + "），如果再搵到同款可以通知我嗎？\n" + url,
      msgGeneral: "你好 Tack, tack!，我想查詢："
    },
    share: "分享", copied: "已複製連結",
    more: b => "更多 " + b + " 貨品",
    alsoLike: "你可能也喜歡",
    shopAll: "查看全部",
    home: "主頁", shop: "選購", crumbs: "導覽路徑", fulfilMore: "送貨及自取詳情",
    filters: { category: "類別", brand: "品牌／設計師", status: "供應狀況", price: "價錢", sort: "排序", reset: "清除篩選" },
    status: { active: "有貨及已留貨", available: "現貨", "on-hold": "已留貨", sold: "已售出", all: "全部" },
    price: { any: "所有價錢", u500: "HK$500 以下", "500-1500": "HK$500–1,500", "1500-5000": "HK$1,500–5,000", o5000: "HK$5,000 以上" },
    sort: { newest: "最新上架", "price-asc": "價錢：低至高", "price-desc": "價錢：高至低", brand: "品牌 A–Z" },
    results: n => "共 " + n + " 件",
    noResults: "暫時未有符合篩選條件的貨品。",
    noResultsCta: "想搵特定款式？WhatsApp 話我知，我們會幫你留意。",
    soldEmpty: "已售出區暫時未有貨品，每件都仲等緊新主人。",
    photoNote: "此為示意插圖，實物相片即將上載；WhatsApp 我們即可索取相片。",
    notFound: "搵唔到這件貨品，可能已改名或下架。",
    dropTitle: d => "Fresh Thursday 新貨 · " + d,
    by: "設計：", for_: "品牌："
  }
};
