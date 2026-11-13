// Packaged products section (Open Food Facts data). Uses the helpers of app.js (api, esc, fmt, crumbs ...).
// API: /api/products/meta  /api/products/list  /api/products/search  /api/product
// Routes:
//   #/p                                   products home
//   #/p/c/<category | all>?m=<market>&sort=<sort>&page=<n>
//   #/p/search/<text or barcode>
//   #/p/i/<barcode>                       product page (barcodes not stored are looked up live)
"use strict";

let PMETA = null, PCATS = {};
async function loadProductMeta() {
  if (PMETA) return;
  PMETA = await api("/api/products/meta");
  PCATS = Object.fromEntries(PMETA.categories.map((c) => [c.id, c]));
  groupbarFor = null;   // build the product group bar again with the categories
}

// Notice shown when a product search is submitted (Enter): the data is user-entered and not checked
// by us. "不再顯示" keeps it hidden in this browser.
function showBetaNotice() {
  const dlg = document.getElementById("betaNotice");
  if (!dlg || dlg.open || localStorage.getItem("hideBetaNotice") === "1") return;
  dlg.showModal();
}
document.getElementById("betaNotice")?.addEventListener("close", () => {
  if (document.getElementById("betaHide").checked) localStorage.setItem("hideBetaNotice", "1");
});
document.getElementById("searchForm").addEventListener("submit", () => {
  if (inProducts() && q.value.trim()) {
    clearTimeout(searchTimer);
    location.hash = `#/p/search/${encodeURIComponent(q.value.trim())}`;
    showBetaNotice();
  }
});

// Products home: everyday Hong Kong products, picked by hand (2026-11-13). Each one has a photo and
// nutrition facts. [barcode, Chinese name shown on the card]
const HK_PICKS = [
  ["4891028703907", "維他檸檬茶（低糖）"], ["4891028172345", "維他奶（低糖麥精豆奶）"], ["4897878000012", "出前一丁"],
  ["4897878100408", "合味道（海鮮味）"], ["0089782032881", "嘉頓生命麵包"], ["4892294101428", "卡樂B 粟一燒"],
  ["4895047047288", "奇華雞蛋卷"], ["0078895100020", "李錦記蠔油"], ["4891014896033", "益力多"],
  ["4893318633536", "維記低脂高鈣奶"], ["4890008171606", "陽光檸檬茶"], ["6937761805022", "寶礦力水特"],
];

const P_ALL = { id: "all", name_zh: "全部包裝食品", name_en: "All products" };
const marketName = (id) => PMETA.markets.find((m) => m.id === id)?.name_zh || id;
const pHref = (cid, o = {}) => {
  const qs = new URLSearchParams(Object.entries(o).filter(([k, v]) => v && !(k === "sort" && v === "popular") && !(k === "page" && +v === 1)));
  return `#/p/c/${cid}${qs.toString() ? "?" + qs : ""}`;
};
// Products with "ml" / "L" in the quantity are drinks: their label values are per 100 ml.
const perUnit = (p) => (/\d\s*(ml|cl|l)\b|毫升|公升|ミリリットル/i.test(p.quantity || "") || p.category === "drinks" || p.category === "alcohol" ? "毫升" : "克");
const ICON_BOX = '<svg class="icon" viewBox="0 0 24 24"><path d="M21 8 12 3 3 8v8l9 5 9-5z"/><path d="m3 8 9 5 9-5M12 13v8"/></svg>';
const thumb = (p, cls = "thumb") => p.image
  ? `<span class="${cls}"><img src="${esc(p.image)}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer"></span>`
  : `<span class="${cls} empty">${ICON_BOX}</span>`;
const nutriBadge = (g) => (g ? `<span class="nutri nutri-${g}" title="Nutri-Score ${g.toUpperCase()}">${g.toUpperCase()}</span>` : "");

function productRow(p) {
  const sub = [p.brand, p.quantity].filter(Boolean).map(esc).join(" · ");
  return `<li><a class="prow" href="#/p/i/${encodeURIComponent(p.code)}">
    ${thumb(p)}
    <span class="pmain"><span class="nm">${esc(p.name)}</span><span class="sub">${sub || '<span class="muted">未有品牌資料</span>'}</span></span>
    <span class="kc">${p.has_nutrition && typeof p.energy_kcal === "number" ? `${Math.round(p.energy_kcal)}<small>kcal/100${perUnit(p) === "毫升" ? "ml" : "g"}</small>` : '<small class="nodata">未有營養資料</small>'}</span>
  </a></li>`;
}

async function productRoute(parts, params) {
  if (parts[0] === "c" && parts[1]) return productCategory(parts[1], params);
  if (parts[0] === "search" && parts[1]) return productSearch(parts[1]);
  if (parts[0] === "i" && parts[1]) return productPage(parts[1]);
  return productsHome();
}

// ---------- products home ----------

async function productsHome() {
  setActiveGroup(null);
  document.title = "包裝食品 - 食物營養資料庫";
  app.innerHTML = `
    <section class="home-hero">
      <h1>包裝食品營養標籤</h1>
      <p>掃描條碼或輸入產品名稱，查看包裝上的營養標籤、成分及致敏物。</p>
      <div class="hero-row">
        <form class="search" id="pHomeSearch" role="search">
          <svg class="icon" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
          <input id="phq" type="search" placeholder="產品名稱、品牌或條碼，例如：維他奶、Calbee" autocomplete="off" aria-label="搜尋包裝食品">
        </form>
        <button type="button" class="scan-cta" id="pScan">
          <svg class="icon" viewBox="0 0 24 24"><path d="M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2"/><path d="M7 8v8M10.5 8v8M14 8v8M17 8v8"/></svg>
          掃描條碼</button>
      </div>
      <div class="meta-line"><a href="#/p/c/all"><b>${PMETA.total.toLocaleString()}</b> 件產品</a> · <b>${PMETA.markets.length}</b> 個亞洲地區 · 資料來源 <b>Open Food Facts</b></div>
    </section>

    <section class="home-section">
      <div class="section-head"><h2>香港人熟悉的產品</h2><a class="eyebrow" href="${pHref("all", { m: "HK" })}">標示在香港有售的產品 ›</a></div>
      <p class="muted section-note">本站挑選的香港常見產品。營養數值來自 Open Food Facts 用戶輸入的包裝標籤，只供參考。</p>
      <div class="pcards" id="pPopular"><p class="muted">載入中…</p></div>
    </section>

    <section class="home-section">
      <div class="section-head"><h2>按地區瀏覽</h2><span class="eyebrow">用戶標示的有售地區</span></div>
      <div class="tabs markets">${PMETA.markets.map((m) => `<a href="${pHref("all", { m: m.id })}">${esc(m.name_zh)} <span class="n">${m.n.toLocaleString()}</span></a>`).join("")}</div>
    </section>

    <section class="home-section">
      <div class="section-head"><h2>產品類別</h2><a class="eyebrow" href="#/p/c/all">全部產品 ›</a></div>
      <div class="grid">${PMETA.categories.map((c) => `
        <a href="#/p/c/${c.id}">
          <span class="txt"><strong>${esc(c.name_zh)}</strong><span class="sub">${esc(c.name_en)}</span></span>
          <span class="count">${c.n.toLocaleString()} 件</span>${ICON_CHEVRON}</a>`).join("")}
      </div>
    </section>

    <section class="home-section">
      <div class="source-card off-card">
        <div class="flag">Open Food Facts</div>
        <div><strong>資料來自 Open Food Facts</strong>
          <span class="sub">全球用戶按包裝標籤輸入的公開資料庫。本站收錄被用戶標示在亞洲地區有售的產品；其他條碼會即時向 Open Food Facts 查詢。</span>
          <span class="sub">${esc(PMETA.source.licence)}</span></div>
      </div>
    </section>`;
  const phq = document.getElementById("phq");
  document.getElementById("pHomeSearch").addEventListener("submit", (e) => {
    e.preventDefault();
    if (!phq.value.trim()) return;
    clearTimeout(searchTimer);
    location.hash = `#/p/search/${encodeURIComponent(phq.value.trim())}`;
    showBetaNotice();
  });
  phq.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      const v = phq.value.trim();
      if (!v) return;
      location.hash = `#/p/search/${encodeURIComponent(v)}`;
      q.value = phq.value;
      q.focus();
    }, 400);
  });
  document.getElementById("pScan").addEventListener("click", openScanner);
  const d = await api(`/api/products/codes?codes=${HK_PICKS.map(([c]) => c).join(",")}`);
  const box = document.getElementById("pPopular");
  if (!box) return;
  const label = Object.fromEntries(HK_PICKS);
  box.innerHTML = d.results.map((p) => ({ ...p, sub: p.name, name: label[p.code] || p.name })).map((p) => `
    <a href="#/p/i/${encodeURIComponent(p.code)}">
      ${thumb(p, "pimg")}
      <div class="nm">${esc(p.name)}</div>
      <div class="sub">${esc([p.brand, p.sub && p.sub !== p.name && p.sub.toLowerCase() !== (p.brand || "").toLowerCase() ? p.sub : p.quantity].filter(Boolean).join(" · "))}</div>
      <div class="kc">${typeof p.energy_kcal === "number" ? Math.round(p.energy_kcal) : "—"}<small>kcal/100${perUnit(p) === "毫升" ? "ml" : "g"}</small>${nutriBadge(p.nutriscore)}</div>
    </a>`).join("");
}

// ---------- category / market list ----------

async function productCategory(cid, params) {
  const c = cid === "all" ? P_ALL : PCATS[cid];
  if (!c) return failed({ status: 404 });
  const m = params.get("m") || "";
  const sort = params.get("sort") || "popular";
  const page = Math.max(parseInt(params.get("page") || "1", 10) || 1, 1);
  setActiveGroup(cid);
  document.title = `${c.name_zh} - 包裝食品 - 食物營養資料庫`;
  loading();
  const qs = new URLSearchParams({ c: cid, sort, page: String(page) });
  if (m) qs.set("m", m);
  const d = await api(`/api/products/list?${qs}`);
  const pages = Math.max(Math.ceil(d.total / d.page_size), 1);
  const href = (o) => pHref(cid, { m, sort, page: 1, ...o });
  app.innerHTML = `
    ${crumbs([["包裝食品", "#/p"], [c.name_zh, ""]])}
    <h1 class="page">${esc(c.name_zh)}${m ? ` <span class="h-sub">· 標示在${esc(marketName(m))}有售</span>` : ""}</h1>
    <p class="muted">${esc(c.name_en)} · ${d.total.toLocaleString()} 件產品</p>
    <div class="tabs filters markets">
      <a href="${href({ m: "" })}" class="${m ? "" : "on"}">所有地區</a>
      ${PMETA.markets.map((x) => `<a href="${href({ m: x.id })}" class="${m === x.id ? "on" : ""}">${esc(x.name_zh)}</a>`).join("")}
    </div>
    <div class="card">
      <div class="toolbar"><span class="eyebrow">每100克 / 毫升 · 第 ${page} / ${pages} 頁</span>
        <select id="psort" aria-label="排序">
          <option value="popular">最多人掃描</option><option value="name">按名稱</option>
          <option value="kcalAsc">卡路里：低至高</option><option value="kcalDesc">卡路里：高至低</option>
          <option value="protein">蛋白質最高</option>
        </select></div>
      <ul class="list plist">${d.results.map(productRow).join("") || '<li class="muted">沒有產品</li>'}</ul>
      ${pages > 1 ? `<nav class="pager" aria-label="分頁">
        ${page > 1 ? `<a href="${href({ page: page - 1 })}">‹ 上一頁</a>` : "<span></span>"}
        <span class="muted">第 ${page} / ${pages} 頁</span>
        ${page < pages ? `<a href="${href({ page: page + 1 })}">下一頁 ›</a>` : "<span></span>"}
      </nav>` : ""}
    </div>`;
  const sel = document.getElementById("psort");
  sel.value = sort;
  sel.onchange = () => { location.hash = href({ sort: sel.value }); };
  window.scrollTo(0, 0);
}

// ---------- search ----------

async function productSearch(term) {
  setActiveGroup(null);
  document.title = `搜尋「${term}」 - 包裝食品 - 食物營養資料庫`;
  if (q.value !== term) q.value = term;
  const d = await api(`/api/products/search?limit=100&q=${encodeURIComponent(term)}`);
  if (location.hash !== `#/p/search/${encodeURIComponent(term)}`) return;   // user kept typing
  // a full barcode that we do not store: go to the product page (live lookup)
  if (d.barcode && !d.results.length && /^\d{8,14}$/.test(term)) { location.replace(`#/p/i/${term}`); return; }
  app.innerHTML = `
    ${crumbs([["包裝食品", "#/p"], ["搜尋", ""]])}
    <h1 class="page">搜尋「${esc(term)}」</h1>
    <p class="muted">找到 ${d.total.toLocaleString()} 件產品${d.total > d.results.length ? `，顯示首 ${d.results.length} 件` : ""}</p>
    <div class="card"><ul class="list plist">${d.results.map(productRow).join("") ||
      `<li class="muted">找不到符合的產品。可以試試<a class="link" href="#/search/${encodeURIComponent(term)}">在「食物」中搜尋「${esc(term)}」</a>，或<button type="button" class="link" onclick="openScanner()">掃描條碼</button>。</li>`}</ul></div>`;
}

// ---------- product page ----------

const P_LABEL = [
  ["energy_kcal", "能量", "major", "kcal"], ["protein", "蛋白質", "major"], ["fat", "總脂肪", "major"],
  ["fat_sat", "飽和脂肪", "sub"], ["fat_trans", "反式脂肪", "sub"], ["fat_mono", "單元不飽和脂肪", "sub", null, true],
  ["fat_poly", "多元不飽和脂肪", "sub", null, true], ["cholesterol", "膽固醇", "", null, true],
  ["carbohydrate", "碳水化合物", "major"], ["sugars", "糖", "sub"], ["fibre", "膳食纖維", "sub", null, true],
  ["sodium", "鈉", "major"],
];

function productLabel(n, factor, servingText) {
  const unit = (id) => NUTRIENTS[id]?.unit || "";
  const val = (id) => (typeof n[id] === "number" ? `${fmtNum(n[id] * factor)} ${unit(id)}` : "—");
  const shown = new Set([...P_LABEL.map((r) => r[0]), "energy_kj", "salt_eq"]);
  const more = Object.keys(n).filter((id) => !shown.has(id) && NUTRIENTS[id]);
  return `
    <div class="label">
      <h3>營養標籤</h3>
      <div class="per">每 <b>${esc(servingText)}</b></div>
      <table>
        ${P_LABEL.filter(([id, , , , optional]) => !optional || id in n)
          .map(([id, t, cls]) => `<tr class="${cls}"><td>${t}</td><td>${val(id)}${id === "energy_kcal" && typeof n.energy_kj === "number" ? `<span class="kj"> / ${fmtNum(n.energy_kj * factor)} kJ</span>` : ""}</td></tr>`).join("")}
        ${more.length ? `<tr class="sec"><td colspan="2">其他營養素</td></tr>
          ${more.map((id) => `<tr><td>${esc(NUTRIENTS[id].name_zh || NUTRIENTS[id].name_en)}</td><td>${val(id)}</td></tr>`).join("")}` : ""}
      </table>
    </div>
    <p class="src">數值按 Open Food Facts 記錄的包裝標籤（每100${esc(servingText.includes("毫升") ? "毫升" : "克")}）換算。「—」表示沒有資料。</p>`;
}

const NOVA = { 1: "未經加工或輕度加工", 2: "烹調用配料", 3: "加工食品", 4: "超加工食品" };

async function productPage(code) {
  loading();
  let d;
  try {
    d = await api(`/api/product?code=${encodeURIComponent(code)}`);
  } catch (e) {
    if (e.status === 404 || e.status === 400) return productNotFound(code);
    throw e;
  }
  const p = d.product, n = p.nutrients || {};
  const cat = PCATS[p.category];
  setActiveGroup(cat ? cat.id : null);
  document.title = `${p.name} 營養標籤 - 包裝食品 - 食物營養資料庫`;
  const u = perUnit(p);
  const servings = [{ text: `100${u}`, g: 100 }];
  if (p.serving_g > 0 && p.serving_g !== 100) servings.push({ text: `每份 ${p.serving_size || fmtNum(p.serving_g) + u}`, g: p.serving_g });
  const markets = (p.markets || "").split(",").filter(Boolean).map(marketName);
  const offUrl = `https://world.openfoodfacts.org/product/${encodeURIComponent(p.code)}`;
  const path = [["包裝食品", "#/p"], ...(cat ? [[cat.name_zh, `#/p/c/${cat.id}`]] : []), [p.name, ""]];

  app.innerHTML = `<div class="food-page product-page">
    ${crumbs(path)}
    ${d.live ? `<div class="notice">本站未收錄這件產品，以下資料即時取自 Open Food Facts。</div>` : ""}
    <section class="card">
      <div class="food-head">
        ${p.image ? `<a class="pphoto" href="${esc(p.image.replace(/\.(\d+)\.jpg$/, ".400.jpg"))}" target="_blank" rel="noopener"><img src="${esc(p.image)}" alt="${esc(p.name)} 包裝相片" referrerpolicy="no-referrer"></a>` : `<span class="pphoto empty">${ICON_BOX}</span>`}
        <div class="phead-txt">
          <h1>${esc(p.name)}</h1>
          <div class="en">${esc([p.brand, p.quantity].filter(Boolean).join(" · "))}${p.generic_name ? `<br><span class="muted">${esc(p.generic_name)}</span>` : ""}</div>
          <div class="chips">
            <span class="pill soft barcode">${esc(p.code)}</span>
            ${p.nutriscore ? `<span class="pill nutri-pill nutri-${p.nutriscore}">Nutri-Score ${p.nutriscore.toUpperCase()}</span>` : ""}
            ${p.nova ? `<span class="pill soft" title="NOVA 加工程度分類">NOVA ${p.nova} · ${NOVA[p.nova]}</span>` : ""}
            ${p.off_category ? `<span class="pill soft">${esc(p.off_category)}</span>` : ""}
          </div>
          ${markets.length ? `<p class="muted desc">用戶標示的有售地區：${markets.map(esc).join("、")}</p>` : p.countries ? `<p class="muted desc">用戶標示的有售地區：${esc(p.countries)}</p>` : ""}
        </div>
      </div>
      ${p.has_nutrition ? `<div class="serving-row">
        <div class="eyebrow" style="margin-bottom:8px">食用分量</div>
        <div class="serving" id="serving">
          ${servings.map((s, i) => `<button type="button" data-g="${s.g}" data-t="${esc(s.text)}" class="${i === 0 ? "on" : ""}">${esc(s.text)}</button>`).join("")}
          <label>自訂 <input type="number" id="grams" min="1" max="5000" step="1" placeholder="${u}" aria-label="自訂分量"> ${u}</label>
        </div>
      </div>
      <div class="kcal-card" id="kcalCard"></div>` : `<div class="empty-nutrition">
        <strong>Open Food Facts 未有這件產品的營養資料。</strong>
        <span>如果你手上有這件產品，可以<a href="${offUrl}" target="_blank" rel="noopener">在 Open Food Facts 補上營養標籤</a>。</span></div>`}
    </section>
    ${p.has_nutrition || p.ingredients ? `<section class="card ai-card" id="aiCard">
      <div class="section-head"><h2>AI 健康評分</h2><span class="eyebrow">DeepSeek</span></div>
      <div id="aiBody"></div>
    </section>` : ""}
    ${p.has_nutrition ? `<div class="two-col">
      <section class="card"><div class="section-head"><h2>主要營養分佈</h2></div><div id="macros"></div></section>
      <section class="card" id="label"></section>
    </div>` : ""}
    ${p.ingredients || p.allergens || p.traces ? `<section class="card">
      <div class="section-head"><h2>成分及致敏物</h2></div>
      ${p.allergens ? `<p class="allergen"><b>致敏物：</b>${esc(p.allergens)}</p>` : ""}
      ${p.traces ? `<p class="allergen soft"><b>可能含有：</b>${esc(p.traces)}</p>` : ""}
      ${p.ingredients ? `<p class="ingredients">${esc(p.ingredients)}</p>` : ""}
      <p class="src">成分按包裝原文記錄，可能是其他語言。</p>
    </section>` : ""}
    ${d.same_brand.length ? `<section class="card"><div class="section-head"><h2>同品牌產品</h2><span class="eyebrow">${esc(p.brand)}</span></div>
      <ul class="list plist">${d.same_brand.map(productRow).join("")}</ul></section>` : ""}
    <p class="src source-line">資料來源：<a class="link" href="${offUrl}" target="_blank" rel="noopener">Open Food Facts</a>${p.last_modified ? ` · 最後更新：${esc(p.last_modified)}` : ""} · 授權：${esc(d.source.licence)}。${esc(d.source.note)}</p>
  </div>`;

  if (document.getElementById("aiBody")) runAi(p.code);   // automatic: saved answers load at once
  if (p.has_nutrition) {
    const nv = Object.fromEntries(Object.entries(n).map(([k, v]) => [k, { value: v }]));   // shape used by macros()
    const render = (amount, text) => {
      const factor = amount / 100;
      document.getElementById("kcalCard").innerHTML = `
        <div><span class="eyebrow">每${esc(text)}</span><div class="big">${fmt(n.energy_kcal, factor)}<small>kcal</small></div></div>
        <div class="pcf">${[["protein", "蛋白質"], ["carbohydrate", "碳水化合物"], ["fat", "脂肪"]].map(([k, l]) =>
          `<div><b>${fmt(n[k], factor)}${typeof n[k] === "number" ? " g" : ""}</b><span>${l}</span></div>`).join("")}</div>`;
      document.getElementById("macros").innerHTML = macros(nv, factor);
      document.getElementById("label").innerHTML = productLabel(n, factor, text);
    };
    const box = document.getElementById("serving");
    const input = document.getElementById("grams");
    box.addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      box.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
      input.value = "";
      render(+b.dataset.g, b.dataset.t);
    });
    input.addEventListener("input", () => {
      const v = +input.value;
      if (v > 0) {
        box.querySelectorAll("button").forEach((x) => x.classList.remove("on"));
        render(v, `${v}${u}`);
      }
    });
    render(100, `100${u}`);
  }
  window.scrollTo(0, 0);
}

// ---------- AI health score ----------

const AI_BANDS = [[90, "excellent"], [70, "good"], [50, "ok"], [30, "poor"], [0, "bad"]];
async function runAi(code) {
  const box = document.getElementById("aiBody");
  if (!box) return;
  box.className = "ai-loading";
  box.innerHTML = '<span class="spinner" aria-hidden="true"></span><span>AI 正在分析這件產品…（首次分析約需 5 至 15 秒）</span>';
  let a;
  try {
    a = await api(`/api/product-ai?code=${encodeURIComponent(code)}`);
  } catch (e) {
    box.className = "ai-start";
    box.innerHTML = `<p class="muted">${e.status === 503 ? "AI 功能尚未設定。" : e.status === 422 ? "這件產品的資料不足，未能分析。" : "暫時未能完成分析，請稍後再試。"}</p>
      ${e.status === 503 || e.status === 422 ? "" : '<button type="button" class="btn-ghost" id="aiGo">再試一次</button>'}`;
    document.getElementById("aiGo")?.addEventListener("click", () => runAi(code));
    return;
  }
  if (document.getElementById("aiBody") !== box) return;   // user went to another page
  const band = AI_BANDS.find(([min]) => a.score >= min)[1];
  const R = 42, C = 2 * Math.PI * R;
  box.className = "ai-result";
  box.innerHTML = `
    <div class="ai-top">
      <svg class="ai-ring band-${band}" viewBox="0 0 100 100" role="img" aria-label="健康分數 ${a.score} 分（滿分100）">
        <circle r="${R}" cx="50" cy="50" fill="none" stroke="var(--track)" stroke-width="9"/>
        <circle class="arc" r="${R}" cx="50" cy="50" fill="none" stroke-width="9" stroke-linecap="round"
          stroke-dasharray="${(a.score / 100) * C} ${C}" transform="rotate(-90 50 50)"/>
        <text x="50" y="52" text-anchor="middle" font-size="28" font-weight="900" fill="var(--ink)">${a.score}</text>
        <text x="50" y="68" text-anchor="middle" font-size="10" font-weight="600" fill="var(--ink-3)">/ 100</text>
      </svg>
      <div>
        <div class="ai-verdict band-${band}">${esc(a.verdict)}</div>
        <p class="ai-summary">${esc(a.summary)}</p>
        ${a.confidence === "low" ? '<span class="pill soft">資料不足，分數只供粗略參考</span>' : ""}
      </div>
    </div>
    ${a.good.length || a.watch.length ? `<div class="ai-lists">
      ${a.good.length ? `<div><h3>優點</h3><ul class="ai-good">${a.good.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>` : ""}
      ${a.watch.length ? `<div><h3>要注意</h3><ul class="ai-watch">${a.watch.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>` : ""}
    </div>` : ""}
    ${a.tip ? `<p class="ai-tip"><b>小貼士：</b>${esc(a.tip)}</p>` : ""}
    <p class="src">由 AI（${esc(a.model)}）根據本頁的標籤資料自動生成，可能有錯，只供參考，不能代替醫生或營養師的意見。</p>`;
}

function productNotFound(code) {
  setActiveGroup(null);
  document.title = "找不到產品 - 包裝食品 - 食物營養資料庫";
  app.innerHTML = `
    ${crumbs([["包裝食品", "#/p"], ["找不到產品", ""]])}
    <section class="card not-found">
      <span class="pphoto empty">${ICON_BOX}</span>
      <div>
        <h1 class="page">找不到條碼 ${esc(code)}</h1>
        <p class="muted">本站及 Open Food Facts 都沒有這個條碼的產品。</p>
        <div class="nf-actions">
          <button type="button" class="scan-cta" onclick="openScanner()">再掃描一次</button>
          <a class="btn-ghost" href="https://world.openfoodfacts.org/cgi/product.pl?type=add&code=${encodeURIComponent(code)}" target="_blank" rel="noopener">在 Open Food Facts 新增產品</a>
        </div>
      </div>
    </section>`;
}

// ---------- barcode scanner ----------
// Native BarcodeDetector (Chrome / Android, Safari 17+ on some devices); otherwise a polyfill
// (barcode-detector, ZXing compiled to WebAssembly, MIT) is loaded on first use.

const BARCODE_FORMATS = ["ean_13", "ean_8", "upc_a", "upc_e", "code_128"];
const POLYFILL = "https://cdn.jsdelivr.net/npm/barcode-detector@3.2.3/dist/iife/polyfill.js";
let detectorP = null, scanStream = null, scanTimer = null;

function getDetector() {
  if (!detectorP) {
    detectorP = (async () => {
      let native = "BarcodeDetector" in window;
      if (native) {
        try {
          const ok = await BarcodeDetector.getSupportedFormats();
          native = BARCODE_FORMATS.some((f) => ok.includes(f));
        } catch { native = false; }
      }
      if (!native) {
        delete window.BarcodeDetector;
        await new Promise((resolve, reject) => {
          const s = document.createElement("script");
          s.src = POLYFILL; s.onload = resolve; s.onerror = () => reject(new Error("polyfill"));
          document.head.appendChild(s);
        });
      }
      return new BarcodeDetector({ formats: BARCODE_FORMATS });
    })().catch((e) => { detectorP = null; throw e; });
  }
  return detectorP;
}

const scanEl = (id) => document.getElementById(id);
const scanStatus = (t, cls = "") => { const s = scanEl("scanStatus"); s.textContent = t; s.className = "scan-status " + cls; };

function foundCode(code) {
  closeScanner();
  if (navigator.vibrate) navigator.vibrate(60);
  location.hash = `#/p/i/${code}`;
}

async function openScanner() {
  const dlg = scanEl("scanner");
  if (dlg.open) return;
  dlg.showModal();
  scanEl("scanCode").value = "";
  scanEl("scanView").classList.remove("off");
  scanStatus("正在開啟相機…");
  if (!navigator.mediaDevices?.getUserMedia) {
    scanEl("scanView").classList.add("off");
    scanStatus("這個瀏覽器不能使用相機。請輸入條碼數字，或用相片掃描。", "warn");
    return;
  }
  try {
    const [stream, detector] = await Promise.all([
      navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false }),
      getDetector(),
    ]);
    if (!dlg.open) { stream.getTracks().forEach((t) => t.stop()); return; }
    scanStream = stream;
    const video = scanEl("scanVideo");
    video.srcObject = stream;
    await video.play();
    scanStatus("把條碼放在框內");
    const tick = async () => {
      if (!scanStream) return;
      try {
        const codes = await detector.detect(video);
        const hit = codes.find((c) => /^\d{6,14}$/.test(c.rawValue));
        if (hit) return foundCode(hit.rawValue);
      } catch { /* frame not ready */ }
      scanTimer = setTimeout(tick, 120);
    };
    tick();
  } catch (e) {
    scanEl("scanView").classList.add("off");
    scanStatus(e && e.name === "NotAllowedError" ? "相機權限被拒絕。請在瀏覽器設定中允許使用相機，或輸入條碼數字。"
      : e && e.message === "polyfill" ? "未能載入條碼掃描工具。請輸入條碼數字。"
      : "未能開啟相機。請輸入條碼數字，或用相片掃描。", "warn");
  }
}

function closeScanner() {
  clearTimeout(scanTimer);
  if (scanStream) scanStream.getTracks().forEach((t) => t.stop());
  scanStream = null;
  const dlg = scanEl("scanner");
  if (dlg.open) dlg.close();
}

(function initScanner() {
  const dlg = scanEl("scanner");
  scanEl("scanBtn").addEventListener("click", openScanner);
  scanEl("scanClose").addEventListener("click", closeScanner);
  dlg.addEventListener("close", closeScanner);
  dlg.addEventListener("click", (e) => { if (e.target === dlg) closeScanner(); });
  scanEl("scanManual").addEventListener("submit", (e) => {
    e.preventDefault();
    const v = scanEl("scanCode").value.replace(/\D/g, "");
    if (/^\d{6,14}$/.test(v)) foundCode(v);
    else scanStatus("條碼應該是 6 至 14 位數字。", "warn");
  });
  scanEl("scanFile").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    e.target.value = "";
    if (!file) return;
    scanStatus("正在讀取相片…");
    try {
      const [detector, bmp] = await Promise.all([getDetector(), createImageBitmap(file)]);
      const codes = await detector.detect(bmp);
      const hit = codes.find((c) => /^\d{6,14}$/.test(c.rawValue));
      if (hit) foundCode(hit.rawValue);
      else scanStatus("相片中找不到條碼。請拍得近一點，條碼要清楚。", "warn");
    } catch {
      scanStatus("未能讀取相片。請輸入條碼數字。", "warn");
    }
  });
})();
