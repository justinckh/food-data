// Food nutrition site. Data comes from the API (Cloudflare Pages Functions + D1):
//   /api/meta  /api/search  /api/food  /api/category  /api/foods
// Routes (hash-based):
//   #/                 home
//   #/c/<category | all>?sub=<subcategory>&src=<source>&sort=<sort>&page=<n>   database-wide category
//   #/f/<food id>      food detail (old CFS ids without "cfs:" still work)
//   #/search/<query>   search results
"use strict";

let META, CATS = {}, NUTRIENTS = {};
const app = document.getElementById("app");
const q = document.getElementById("q");
const cache = new Map();

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
// API_VERSION is added to every API address, so a new release never reads answers that a
// browser or the edge cached for the previous release. Change it when the API or data changes.
// Machine-translated Chinese names (foods.zh_mt): the tag is hidden for now (user request 2026-11-12).
const SHOW_MT_TAG = false;
const API_VERSION = "2026-11-13j";
const api = (path) => {
  if (!cache.has(path)) {
    const url = path + (path.includes("?") ? "&" : "?") + "v=" + API_VERSION;
    cache.set(path, fetch(url).then((r) => {
      if (!r.ok) throw Object.assign(new Error(`HTTP ${r.status}`), { status: r.status });
      return r.json();
    }).catch((e) => { cache.delete(path); throw e; }));
  }
  return cache.get(path);
};

// Home page picks: everyday Hong Kong foods (CFS ids), and quick search chips.
const FEATURED = ["070100F007661", "10160100028", "10060600763", "10400200840", "10010700715", "070703F002594", "10030200339", "10400200002"];
const QUICK = ["白飯", "奶茶", "雞蛋", "蘋果", "豆腐", "三文魚", "叉燒", "西蘭花"];

const COUNTRY = { HK: "香港", TW: "台灣", JP: "日本", AU: "澳洲", US: "美國", GB: "英國", CA: "加拿大", FR: "法國" };
const SOURCE_SHORT = { cfs: "香港 食物安全中心", tfda: "台灣 衛福部食藥署", mext: "日本 文部科學省", afcd: "澳洲 FSANZ",
  usda_fnd: "美國 USDA Foundation", usda_sr: "美國 USDA SR Legacy", cofid: "英國 CoFID", cnf: "加拿大 CNF" };
const CARB_METHOD = { total: "總量", difference: "差減法", available: "可利用", available_monosaccharide: "可利用 (單醣當量)", summation: "加總法" };

const ICON_CHEVRON = '<svg class="icon" viewBox="0 0 24 24"><path d="m9 18 6-6-6-6"/></svg>';

function fmtNum(x) {
  if (x === 0) return "0";
  const d = Math.abs(x) >= 100 ? 0 : Math.abs(x) >= 10 ? 1 : 2;
  return String(+x.toFixed(d));
}
// v: {value, flag, estimated} from the API, or a bare number
function fmt(v, factor = 1) {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return fmtNum(v * factor);
  if (v.flag === "TRACE") return "微量";
  if (v.flag === "ND") return "未驗出";
  if (v.value === null || v.value === undefined) return "—";
  return (v.estimated ? "≈" : "") + fmtNum(v.value * factor);
}
// Sampling dates are not shown in names (user request); the year is shown as a tag instead.
// Same rule as pipeline/versions.py: (2018) (2021年取樣) (2020取樣) (2月) and dates inside (12月,雄魚).
const stripDate = (n) => !n ? n : n
  .replace(/\s*[(（]\s*(?:(?:19|20)\d{2,3}\s*年?\s*(?:取樣)?|\d{1,2}\s*月\s*(?:取樣)?)\s*[)）]/g, "")
  .replace(/[(（]\s*(?:(?:19|20)\d{2,3}\s*年?\s*(?:取樣)?|\d{1,2}\s*月\s*(?:取樣)?)\s*[,，、]\s*/g, "(")
  .replace(/\s*[,，、]\s*(?:(?:19|20)\d{2,3}\s*年?\s*(?:取樣)?|\d{1,2}\s*月\s*(?:取樣)?)\s*(?=[)）])/g, "")
  .replace(/\s*[(（]?\s*(?:19|20)\d{2,3}\s*年取樣\s*[)）]?/g, "")
  .trim();
const name = (f) => f.display_zh || f.display_en || f.name_en || f.name_local || f.id;
const subName = (f) => (f.display_zh && f.display_en ? f.display_en : "");
const kcal = (f) => (typeof f.energy_kcal === "number" ? Math.round(f.energy_kcal) : "—");
const num = (v) => (typeof v === "number" ? v : 0);

function crumbs(items) {
  const out = items.filter((it, i) => i === 0 || it[0] !== items[i - 1][0]);
  return `<nav class="crumbs" aria-label="路徑">${out.map(([t, href], i) =>
    (i ? ICON_CHEVRON : "") + (i < out.length - 1 ? `<a href="${href}">${esc(t)}</a>` : `<span>${esc(t)}</span>`)).join("")}</nav>`;
}

function foodRow(f, extra = "") {
  const multi = f.n_sources > 1 ? `<span class="pill soft">${f.n_sources} 個來源</span>` : "";
  if (extra === "" && f.source_id) extra = `${subName(f) ? " · " : ""}${esc(SOURCE_SHORT[f.source_id] || f.source_id)}`;
  return `<li><a href="#/f/${encodeURIComponent(f.id)}">
    <span><span class="nm">${esc(name(f))}</span> ${multi}<br><span class="sub">${esc(subName(f))}${extra}</span></span>
    <span class="kc">${kcal(f)}<small>kcal/100g</small></span></a></li>`;
}

function setActiveGroup(c) {
  document.querySelectorAll("#groupbar a").forEach((a) => a.classList.toggle("on", a.dataset.g === c));
}
const catHref = (id, o = {}) => {
  const qs = new URLSearchParams(Object.entries(o).filter(([, v]) => v && v !== "name" && v !== 1 && v !== "1"));
  return `#/c/${id}${qs.toString() ? "?" + qs : ""}`;
};
const loading = () => { app.innerHTML = '<p class="muted">載入中…</p>'; };
const failed = (e) => {
  app.innerHTML = e && e.status === 404 ? '<p>找不到此頁。<a href="#/">返回首頁</a></p>'
    : '<p>暫時無法載入資料，請稍後再試。</p>';
};

// ---------- pages ----------

async function home() {
  setActiveGroup(null);
  document.title = "食物營養資料庫";
  app.innerHTML = `
    <section class="home-hero">
      <h1>搜尋食物營養</h1>
      <p>卡路里、蛋白質、脂肪、碳水化合物、礦物質及維他命，可按份量換算。</p>
      <form class="search" id="homeSearch" role="search">
        <svg class="icon" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
        <input id="hq" type="search" placeholder="輸入食物名稱，例如：虎蝦、白飯、apple" autocomplete="off" aria-label="搜尋食物">
      </form>
      <div class="quick">${QUICK.map((w) => `<a href="#/search/${encodeURIComponent(w)}">${w}</a>`).join("")}</div>
      <div class="meta-line"><a href="#/c/all"><b>${META.main_records.toLocaleString()}</b> 種食物</a> · <b>${META.categories.length}</b> 個類別 · <b>${META.sources.length}</b> 個官方資料來源 · <b>${META.nutrients.length}</b> 項營養素</div>
    </section>

    <section class="home-section">
      <div class="section-head"><h2>常見食物</h2><span class="eyebrow">每100克</span></div>
      <div class="featured" id="featured"><p class="muted">載入中…</p></div>
    </section>

    <section class="home-section">
      <div class="section-head"><h2>食物類別</h2><a class="eyebrow" href="#/c/all">瀏覽全部食物 ›</a></div>
      <div class="grid">${META.categories.map((c) => `
        <a href="${catHref(c.id)}">
          <span class="txt"><strong>${esc(c.name_zh)}</strong><span class="sub">${esc(c.name_en)}</span></span>
          <span class="count">${c.n.toLocaleString()} 種</span>${ICON_CHEVRON}</a>`).join("")}
      </div>
    </section>

    <section class="home-section">
      <div class="section-head"><h2>資料來源</h2><span class="eyebrow">各地政府公開資料</span></div>
      <div class="sources">${META.sources.map((x) => `
        <div class="source-card">
          <div class="flag">${esc(COUNTRY[x.country] || x.country)}</div>
          <div><strong>${esc(x.name)}</strong><span class="sub">${esc(x.publisher || "")}${x.version ? ` · ${esc(x.version)}` : ""}</span>
          <span class="sub">${x.foods.toLocaleString()} 項記錄 · ${esc(x.licence || "")}</span></div>
        </div>`).join("")}
      </div>
    </section>`;
  const hq = document.getElementById("hq");
  document.getElementById("homeSearch").addEventListener("submit", (e) => {
    e.preventDefault();
    if (hq.value.trim()) location.hash = `#/search/${encodeURIComponent(hq.value.trim())}`;
  });
  hq.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      const v = hq.value.trim();
      if (!v) return;
      location.hash = `#/search/${encodeURIComponent(v)}`;
      q.value = hq.value;
      q.focus();
    }, 400);
  });
  const { results } = await api(`/api/foods?ids=${FEATURED.join(",")}`);
  const box = document.getElementById("featured");
  if (!box) return;
  box.innerHTML = results.map((f) => {
    const kc = { protein: num(f.protein) * 4, carb: num(f.carbohydrate) * 4, fat: num(f.fat) * 9 };
    const t = kc.protein + kc.carb + kc.fat || 1;
    return `<a href="#/f/${encodeURIComponent(f.id)}">
      <div><div class="nm">${esc(name(f))}</div><div class="sub">${esc(subName(f))}</div></div>
      <div class="kc">${kcal(f)}<small>kcal</small></div>
      <div class="stack">${["protein", "carb", "fat"].map((k) => `<i style="width:${(kc[k] / t) * 100}%;background:var(--${k})"></i>`).join("")}</div>
      <div class="pcf"><span>P <b>${fmt(f.protein)}</b></span><span>C <b>${fmt(f.carbohydrate)}</b></span><span>F <b>${fmt(f.fat)}</b></span></div>
    </a>`;
  }).join("");
}

const ALL_CAT = { id: "all", name_zh: "全部食物", name_en: "All foods" };

async function category(cid, params) {
  const c = cid === "all" ? ALL_CAT : CATS[cid];
  if (!c) return failed({ status: 404 });
  const sub = params.get("sub") || "";
  const src = "";   // source filter removed (user request 2026-11-12); the API still supports src
  const sort = params.get("sort") || "name";
  const page = Math.max(parseInt(params.get("page") || "1", 10) || 1, 1);
  setActiveGroup(cid);
  document.title = `${c.name_zh} - 食物營養資料庫`;
  loading();
  const qs = new URLSearchParams({ c: cid, sort, page: String(page) });
  if (src) qs.set("src", src);
  if (sub) qs.set("sub", sub);
  const d = await api(`/api/category?${qs}`);
  const pages = Math.max(Math.ceil(d.total / d.page_size), 1);
  const href = (o) => catHref(cid, { sub, src, sort, page: 1, ...o });
  const scope = d.subcategory || d.category;
  const path = [["首頁", "#/"], [c.name_zh, sub ? catHref(cid) : ""], ...(d.subcategory ? [[d.subcategory.name_zh, ""]] : [])];
  app.innerHTML = `
    ${crumbs(path)}
    <h1 class="page">${esc(scope.name_zh)}</h1>
    <p class="muted">${esc(scope.name_en)} · ${scope.n.toLocaleString()} 種食物</p>
    ${d.subcategories.length ? `<div class="tabs filters subs">
      <a href="${href({ sub: "" })}" class="${sub ? "" : "on"}">全部${esc(c.name_zh)} (${c.n.toLocaleString()})</a>
      ${d.subcategories.map((x) => `<a href="${href({ sub: x.id })}" class="${sub === x.id ? "on" : ""}">${esc(x.name_zh)} (${x.n.toLocaleString()})</a>`).join("")}
    </div>` : ""}
    <div class="card">
      <div class="toolbar"><span class="eyebrow">每100克 · 第 ${page} / ${pages} 頁</span>
        <select id="sort" aria-label="排序">
          <option value="name">按名稱</option><option value="kcalAsc">卡路里：低至高</option>
          <option value="kcalDesc">卡路里：高至低</option><option value="protein">蛋白質最高</option>
        </select></div>
      <ul class="list">${d.results.map((f) => foodRow(f)).join("") || '<li class="muted">沒有食物</li>'}</ul>
      ${pages > 1 ? `<nav class="pager" aria-label="分頁">
        ${page > 1 ? `<a href="${href({ page: page - 1 })}">‹ 上一頁</a>` : "<span></span>"}
        <span class="muted">第 ${page} / ${pages} 頁</span>
        ${page < pages ? `<a href="${href({ page: page + 1 })}">下一頁 ›</a>` : "<span></span>"}
      </nav>` : ""}
    </div>`;
  const sel = document.getElementById("sort");
  sel.value = sort;
  sel.onchange = () => { location.hash = href({ sort: sel.value }); };
  window.scrollTo(0, 0);
}

function macros(n, factor) {
  const kc = { protein: num(n.protein?.value) * 4, carb: num(n.carbohydrate?.value) * 4, fat: num(n.fat?.value) * 9 };
  const total = kc.fat + kc.carb + kc.protein;
  const pct = (k) => (total ? Math.round((kc[k] / total) * 100) : 0);
  const parts = [["protein", "蛋白質", "protein"], ["carb", "碳水化合物", "carbohydrate"], ["fat", "脂肪", "fat"]];
  const R = 70, C = 2 * Math.PI * R;
  let offset = 0;
  const arcs = total ? parts.map(([k]) => {
    const len = (kc[k] / total) * C;
    const arc = `<circle r="${R}" cx="90" cy="90" fill="none" stroke="var(--${k})" stroke-width="20"
      stroke-dasharray="${len} ${C - len}" stroke-dashoffset="${-offset}" transform="rotate(-90 90 90)"/>`;
    offset += len;
    return arc;
  }).join("") : "";
  return `
    <div class="ring">
      <svg viewBox="0 0 180 180" role="img" aria-label="卡路里來源分佈">
        <circle r="${R}" cx="90" cy="90" fill="none" stroke="var(--track)" stroke-width="20"/>${arcs}
        <text x="90" y="92" text-anchor="middle" font-size="34" font-weight="900" fill="var(--ink)" letter-spacing="-1">${fmt(n.energy_kcal, factor)}</text>
        <text x="90" y="114" text-anchor="middle" font-size="13" font-weight="600" fill="var(--ink-3)">kcal</text>
      </svg>
    </div>
    <div class="bars">${parts.map(([k, label, id]) => `
      <div class="bar-row">
        <div class="top"><span class="nm">${label}</span><span class="v">${pct(k)}%<small>${fmt(n[id], factor)} g</small></span></div>
        <div class="bar"><i style="width:${pct(k)}%;background:var(--${k})"></i></div>
      </div>`).join("")}
    </div>
    <p class="note">熱量佔比：1克蛋白質 = 4 kcal、1克碳水化合物 = 4 kcal、1克脂肪 = 9 kcal</p>`;
}

const LABEL_ROWS = [
  ["energy_kcal", "能量", "major"], ["protein", "蛋白質", "major"], ["fat", "總脂肪", "major"],
  ["fat_sat", "飽和脂肪", "sub"], ["fat_trans", "反式脂肪", "sub"], ["cholesterol", "膽固醇", ""],
  ["carbohydrate", "碳水化合物", "major"], ["sugars", "糖", "sub"], ["fibre", "膳食纖維", "sub"], ["sodium", "鈉", "major"],
];
const MINERALS = ["potassium", "calcium", "magnesium", "phosphorus", "iron", "zinc", "copper", "manganese", "vitamin_c"];

function label(n, factor, servingText) {
  const row = (id, title, cls) => {
    const v = n[id];
    let t = title;
    if (id === "carbohydrate" && v?.method && CARB_METHOD[v.method]) t += ` (${CARB_METHOD[v.method]})`;
    if (id === "fibre" && v?.method === "insoluble") t += " (只計不溶性)";
    const unit = v && typeof v.value === "number" ? " " + (NUTRIENTS[id]?.unit || "") : "";
    return `<tr class="${cls}"><td>${t}</td><td>${fmt(v, factor)}${unit}</td></tr>`;
  };
  const shown = new Set([...LABEL_ROWS.map((r) => r[0]), ...MINERALS, "energy_kcal_source"]);   // source energy: in the kcal note
  const more = Object.keys(n).filter((id) => !shown.has(id) && NUTRIENTS[id]);
  return `
    <div class="label">
      <h3>營養標籤</h3>
      <div class="per">每份食用分量：<b>${esc(servingText)}</b></div>
      <table>
        ${LABEL_ROWS.map(([id, t, cls]) => row(id, t, cls)).join("")}
        <tr class="sec"><td colspan="2">礦物質和維他命</td></tr>
        ${MINERALS.map((id) => row(id, NUTRIENTS[id]?.name_zh || id, "")).join("")}
        ${more.length ? `<tr class="sec"><td colspan="2">其他營養素</td></tr>
          ${more.map((id) => row(id, NUTRIENTS[id].name_zh || NUTRIENTS[id].name_en, "")).join("")}` : ""}
      </table>
    </div>
    <p class="src">「—」表示沒有資料；「≈」表示資料來源的估算值。</p>`;
}

function servingLabel(s) {
  const unit = s.unit === "ml" ? "毫升" : "克";
  const lbl = s.label_zh || s.label_en || "1份";
  return `${lbl} (${fmtNum(s.amount)}${unit})`;
}

async function food(id) {
  loading();
  const d = await api(`/api/food?id=${encodeURIComponent(id)}`);
  const f = d.food;
  const n = Object.fromEntries(d.nutrients.map((x) => [x.id, x]));
  const cat = CATS[f.category];
  setActiveGroup(cat ? cat.id : null);
  document.title = `${name(f)} 營養及卡路里 - 食物營養資料庫`;

  const servings = [{ text: "100克", g: 100 }];
  for (const s of d.servings.slice(0, 6)) if (s.amount !== 100) servings.push({ text: servingLabel(s), g: s.amount });

  const original = [...new Set([f.name_zh, f.name_local, f.name_en].map(stripDate))]
    .filter((x) => x && x !== f.display_zh && x !== f.display_en);
  // a machine-translated name: the original name stays visible under the title (subName)
  const country = COUNTRY[d.source?.country] || d.source?.country || "";
  const path = [["首頁", "#/"], ...(cat ? [[cat.name_zh, catHref(cat.id)]] : []), [name(f), ""]];
  const noteText = (n) => (n ? (/^\d{4}$/.test(n) ? `${n}年數據` : `${n}取樣`) : "");
  const shown = d.members.filter((m) => !m.is_copy);
  const copies = d.members.filter((m) => m.is_copy);

  const linkText = { exact_copy: "相同數據", equivalent: "同一食物" };
  app.innerHTML = `<div class="food-page">
    ${crumbs(path)}
    <section class="card">
      <div class="food-head">
        <div>
          <h1>${esc(name(f))}</h1>
          <div class="en">${esc(subName(f))}</div>
          <div class="chips">
            <span class="pill">${esc(SOURCE_SHORT[f.source_id] || f.source_id)}</span>
            ${f.sample_note ? `<span class="pill soft">${esc(noteText(f.sample_note))}</span>` : ""}
            ${f.zh_mt && SHOW_MT_TAG ? `<span class="pill soft" title="這個中文名稱由機器翻譯，請以原名為準">機器翻譯</span>` : ""}
            ${original.map((o) => `<span class="pill soft">原名 ${esc(o)}</span>`).join("")}
            ${f.alias ? f.alias.split(/[、,]/).slice(0, 6).map((a) => `<span class="pill soft">又名 ${esc(a.replace(/[\[\]]/g, ""))}</span>`).join("") : ""}
          </div>
          ${f.description ? `<p class="muted desc">${esc(f.description)}</p>` : ""}
        </div>
      </div>
      <div class="serving-row">
        <div>
          <div class="eyebrow" style="margin-bottom:8px">食用分量</div>
          <div class="serving" id="serving">
            ${servings.map((s, i) => `<button type="button" data-g="${s.g}" data-t="${esc(s.text)}" class="${i === 0 ? "on" : ""}">${esc(s.text)}</button>`).join("")}
            <label>自訂 <input type="number" id="grams" min="1" max="5000" step="1" placeholder="克" aria-label="自訂克數"> 克</label>
          </div>
        </div>
      </div>
      <div class="kcal-card" id="kcalCard"></div>
    </section>
    <div class="two-col">
      <section class="card"><div class="section-head"><h2>主要營養分佈</h2></div><div id="macros"></div></section>
      <section class="card" id="label"></section>
    </div>
    ${shown.length || copies.length ? `<section class="card"><div class="section-head"><h2>其他來源的數據</h2><span class="eyebrow">每100克</span></div>
      <div class="table-wrap"><table class="others">
        <thead><tr><th>來源</th><th>原名</th><th>kcal</th><th>蛋白質</th><th>脂肪</th><th>碳水</th><th></th></tr></thead>
        <tbody>${shown.map((m) => `<tr>
          <td>${esc(SOURCE_SHORT[m.source_id] || m.source_name)}</td>
          <td><a href="#/f/${encodeURIComponent(m.id)}">${esc(stripDate(m.name_zh || m.name_local || m.name_en))}</a>${m.sample_note ? ` <span class="sub">${esc(noteText(m.sample_note))}</span>` : ""}</td>
          <td>${fmt(m.energy_kcal)}</td><td>${fmt(m.protein)}</td><td>${fmt(m.fat)}</td><td>${fmt(m.carbohydrate)}</td>
          <td>${m.link_to_this ? `<span class="pill soft">${linkText[m.link_to_this] || ""}</span>` : ""}</td></tr>`).join("")}</tbody>
      </table></div>
      ${copies.length ? `<p class="src">另有 ${copies.length} 項記錄與上列數據相同，已隱藏（${[...new Set(copies.map((m) => SOURCE_SHORT[m.source_id] || m.source_id))].map(esc).join("、")}）。</p>` : ""}
      <p class="src">不同地區的分析方法及定義可能不同（例如碳水化合物），數值只供比較參考。</p>
    </section>` : ""}
    ${d.similar.length ? `<section class="card"><div class="section-head"><h2>近似食物</h2></div>
      <ul class="list">${d.similar.map((x) => foodRow(x)).join("")}</ul></section>` : ""}
    <section class="card"><div class="section-head"><h2>相關食物</h2><span class="eyebrow">${esc(SOURCE_SHORT[f.source_id] || "")} · ${esc(f.subgroup_zh || f.group_zh || f.subgroup_en || f.group_en || "")}</span></div>
      <ul class="list">${d.related.map((x) => foodRow(x)).join("") || '<li class="muted">沒有相關食物</li>'}</ul>
    </section>
    <p class="src source-line">資料來源：${esc(d.source?.attribution || d.source?.name || "")}${country ? `（${esc(country)}）` : ""}${d.source?.licence ? ` · 授權：${esc(d.source.licence)}` : ""}${d.source?.version ? ` · 版本：${esc(d.source.version)}` : ""}</p>
  </div>`;

  // values the source did not measure (e.g. UK stock cubes have no energy or carbohydrate)
  const has = (id) => n[id] && (typeof n[id].value === "number" || n[id].flag);
  const missing = [["energy_kcal", "熱量"], ["carbohydrate", "碳水化合物"]].filter(([id]) => !has(id)).map(([, t]) => t);
  // energy: one standard for all sources (pipeline/serve_db.py); show the source's own figure too
  const e = n.energy_kcal, es = n.energy_kcal_source;
  const stdNote = e && e.method === "standard"
    ? `熱量按統一標準計算（蛋白質4、脂肪9、可利用碳水化合物4、膳食纖維2、酒精7 kcal/克）${es && typeof es.value === "number" && Math.abs(es.value - e.value) >= 1 ? `；資料來源數值為 ${fmtNum(es.value)} kcal` : ""}。`
    : "";
  const render = (grams, text) => {
    const factor = grams / 100;
    document.getElementById("kcalCard").innerHTML = `
      <div><span class="eyebrow">每${esc(text)}</span><div class="big">${fmt(n.energy_kcal, factor)}<small>kcal</small></div></div>
      <div class="pcf">${[["protein", "蛋白質"], ["carbohydrate", "碳水化合物"], ["fat", "脂肪"]].map(([k, l]) =>
        `<div><b>${fmt(n[k], factor)}${n[k] && typeof n[k].value === "number" ? " g" : ""}</b><span>${l}</span></div>`).join("")}</div>
      ${stdNote ? `<p class="kc-note">${stdNote}</p>` : ""}
      ${missing.length ? `<p class="kc-note">資料來源沒有量度這個食物的${missing.join("及")}，所以顯示「—」（不等於零）。</p>` : ""}`;
    document.getElementById("macros").innerHTML = macros(n, factor);
    document.getElementById("label").innerHTML = label(n, factor, text);
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
      render(v, `${v}克`);
    }
  });
  render(100, "100克");
  window.scrollTo(0, 0);
}

async function search(term) {
  setActiveGroup(null);
  document.title = `搜尋「${term}」 - 食物營養資料庫`;
  if (q.value !== term) q.value = term;
  const d = await api(`/api/search?limit=100&q=${encodeURIComponent(term)}`);
  if (location.hash !== `#/search/${encodeURIComponent(term)}`) return;   // user kept typing
  app.innerHTML = `
    ${crumbs([["首頁", "#/"], ["搜尋", ""]])}
    <h1 class="page">搜尋「${esc(term)}」</h1>
    <p class="muted">找到 ${d.total} 種食物${d.total > d.results.length ? `，顯示首 ${d.results.length} 種` : ""}</p>
    <div class="card"><ul class="list">${d.results.map((f) => foodRow(f)).join("") ||
      '<li class="muted">很抱歉，找不到符合的食物。</li>'}</ul></div>`;
}

async function route() {
  document.body.classList.toggle("is-home", !/^#\/(f|c|search)\//.test(location.hash));
  const [path, query = ""] = location.hash.replace(/^#\/?/, "").split("?");
  const parts = path.split("/").map(decodeURIComponent);
  try {
    if (parts[0] === "f" && parts[1]) await food(parts[1]);
    else if (parts[0] === "c" && parts[1]) await category(parts[1], new URLSearchParams(query));
    else if (parts[0] === "search" && parts[1]) await search(parts[1]);
    else await home();
  } catch (e) {
    failed(e);
  }
}

// ---------- boot ----------

let searchTimer;
q.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    const v = q.value.trim();
    location.hash = v ? `#/search/${encodeURIComponent(v)}` : "#/";
  }, 250);
});
document.getElementById("searchForm").addEventListener("submit", (e) => e.preventDefault());

api("/api/meta")
  .then((meta) => {
    META = meta;
    CATS = Object.fromEntries(meta.categories.map((c) => [c.id, c]));
    NUTRIENTS = Object.fromEntries(meta.nutrients.map((x) => [x.id, x]));
    document.getElementById("groupbar").innerHTML = `<a href="#/c/all" data-g="all">全部</a>` + meta.categories
      .map((c) => `<a href="${catHref(c.id)}" data-g="${c.id}">${esc(c.name_zh)}</a>`).join("");
    window.addEventListener("hashchange", route);
    route();
  })
  .catch(() => { app.innerHTML = "<p>暫時無法載入資料，請稍後再試。</p>"; });
