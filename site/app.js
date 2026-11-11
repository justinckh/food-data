// Food nutrition site. Routes (hash-based so it works on any static host):
//   #/                 home: food groups
//   #/g/<fg>[/<sub>]   food group, optional subgroup
//   #/f/<food_id>      food detail
//   #/search/<query>   search results
"use strict";

let DB, BY_ID, GROUPS;
const app = document.getElementById("app");
const q = document.getElementById("q");

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

function fmt(v, factor = 1) {
  if (v === null || v === undefined) return "—";
  if (v === "Trace") return "微量";
  if (v === "ND") return "未驗出";
  const x = v * factor;
  if (x === 0) return "0";
  const d = x >= 100 ? 0 : x >= 10 ? 1 : 2;
  return String(+x.toFixed(d));
}
// Home page picks: everyday Hong Kong foods (food_id), and quick search chips.
const FEATURED = ["070100F007661", "10160100028", "10060600763", "10400200840", "10010700715", "070703F002594", "10030200339", "10400200002"];
const QUICK = ["白飯", "奶茶", "雞蛋", "蘋果", "豆腐", "三文魚", "叉燒"];

const ICON_CHEVRON = '<svg class="icon" viewBox="0 0 24 24"><path d="m9 18 6-6-6-6"/></svg>';
const ICON_CHECK = '<svg class="icon" viewBox="0 0 24 24"><path d="M20 6 9 17l-5-5"/></svg>';

// [[label, href], ...]; the last item is the current page. Consecutive duplicate labels
// (e.g. 酒精飲料 › 酒精飲料, where a group has a single subgroup of the same name) are dropped.
function crumbs(items) {
  const out = items.filter((it, i) => i === 0 || it[0] !== items[i - 1][0]);
  return `<nav class="crumbs" aria-label="路徑">${out.map(([t, href], i) =>
    (i ? ICON_CHEVRON : "") + (i < out.length - 1 ? `<a href="${href}">${esc(t)}</a>` : `<span>${esc(t)}</span>`)).join("")}</nav>`;
}

const num = (v) => (typeof v === "number" ? v : 0);
const kcal = (f) => (typeof f.n.energy === "number" ? Math.round(f.n.energy) : "—");

function foodRow(f, extra = "") {
  const g = GROUPS[f.g];
  return `<li><a href="#/f/${f.id}">
    <span><span class="nm">${esc(f.zh)}</span><br><span class="sub">${esc(f.en)}${extra === null ? "" : extra || ` · ${esc(g.subs[f.s].zh)}`}</span></span>
    <span class="kc">${kcal(f)}<small>kcal/100g</small></span></a></li>`;
}

function setActiveGroup(fg) {
  document.querySelectorAll("#groupbar a").forEach((a) => a.classList.toggle("on", a.dataset.g === fg));
}

// ---------- pages ----------

function home() {
  setActiveGroup(null);
  document.title = "食物營養資料庫";
  const subs = DB.groups.reduce((n, g) => n + g.subs.length, 0);
  const featured = FEATURED.map((id) => BY_ID[id]).filter(Boolean);
  app.innerHTML = `
    <section class="home-hero">
      <h1>搜尋食物營養</h1>
      <p>卡路里、蛋白質、脂肪、碳水化合物及礦物質，可按份量換算。</p>
      <form class="search" id="homeSearch" role="search">
        <svg class="icon" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
        <input id="hq" type="search" placeholder="輸入食物名稱，例如：虎蝦、白飯、apple" autocomplete="off" aria-label="搜尋食物">
      </form>
      <div class="quick">${QUICK.map((w) => `<a href="#/search/${encodeURIComponent(w)}">${w}</a>`).join("")}</div>
      <div class="meta-line"><b>${DB.foods.length.toLocaleString()}</b> 種食物 · <b>${DB.groups.length}</b> 個類別 · <b>${subs}</b> 個細分類別 · <b>19</b> 項營養素</div>
    </section>

    <section class="home-section">
      <div class="section-head"><h2>常見食物</h2><span class="eyebrow">每100克</span></div>
      <div class="featured">${featured.map((f) => {
        const kc = { protein: num(f.n.protein) * 4, carb: num(f.n.carb) * 4, fat: num(f.n.fat) * 9 };
        const t = kc.protein + kc.carb + kc.fat || 1;
        return `<a href="#/f/${f.id}">
          <div><div class="nm">${esc(f.zh)}</div><div class="sub">${esc(f.en)}</div></div>
          <div class="kc">${kcal(f)}<small>kcal</small></div>
          <div class="stack">${["protein", "carb", "fat"].map((k) => `<i style="width:${(kc[k] / t) * 100}%;background:var(--${k})"></i>`).join("")}</div>
          <div class="pcf"><span>P <b>${fmt(f.n.protein)}</b></span><span>C <b>${fmt(f.n.carb)}</b></span><span>F <b>${fmt(f.n.fat)}</b></span></div>
        </a>`;
      }).join("")}</div>
    </section>

    <section class="home-section">
      <div class="section-head"><h2>食物類別</h2></div>
      <div class="grid">${DB.groups.map((g) => `
        <a href="#/g/${g.id}">
          <span class="txt"><strong>${esc(g.zh)}</strong><span class="sub">${esc(g.en)}</span></span>
          <span class="count">${g.subs.reduce((n, s) => n + s.n, 0)} 種</span>${ICON_CHEVRON}</a>`).join("")}
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
      // keep typing: the results page swaps this box out for the header search
      q.value = hq.value;
      q.focus();
    }, 400);
  });
}

function group(fg, subId, sort = "name") {
  const g = GROUPS[fg];
  if (!g) return notFound();
  setActiveGroup(fg);
  document.title = `${g.zh} - 食物營養資料庫`;
  const sub = subId === undefined ? null : g.subs[+subId];
  let foods = DB.foods.filter((f) => f.g === fg && (!sub || f.s === sub.id));
  const sorters = {
    name: (a, b) => a.zh.localeCompare(b.zh, "zh-Hant"),
    kcalAsc: (a, b) => num(a.n.energy) - num(b.n.energy),
    kcalDesc: (a, b) => num(b.n.energy) - num(a.n.energy),
    protein: (a, b) => num(b.n.protein) - num(a.n.protein),
  };
  foods = foods.sort(sorters[sort] || sorters.name);
  const base = `#/g/${fg}`;
  app.innerHTML = `
    ${crumbs([["首頁", "#/"], [g.zh, base], ...(sub ? [[sub.zh, ""]] : [])])}
    <h1 class="page">${esc(sub ? sub.zh : g.zh)}</h1>
    <p class="muted">${esc(sub ? sub.en : g.en)} · ${foods.length} 種食物</p>
    ${g.subs.length > 1 ? `<div class="tabs">
      <a href="${base}" class="${sub ? "" : "on"}">全部</a>
      ${g.subs.map((s) => `<a href="${base}/${s.id}" class="${sub && sub.id === s.id ? "on" : ""}">${esc(s.zh)} (${s.n})</a>`).join("")}
    </div>` : ""}
    <div class="card">
      <div class="toolbar"><span class="eyebrow">每100克</span>
        <select id="sort" aria-label="排序">
          <option value="name">按名稱</option><option value="kcalAsc">卡路里：低至高</option>
          <option value="kcalDesc">卡路里：高至低</option><option value="protein">蛋白質最高</option>
        </select></div>
      <ul class="list">${foods.map((f) => foodRow(f, !sub && g.subs.length > 1 ? undefined : null)).join("")}</ul>
    </div>`;
  const sel = document.getElementById("sort");
  sel.value = sort;
  sel.onchange = () => group(fg, subId, sel.value);
}

function macros(f, factor) {
  const kc = { protein: num(f.n.protein) * 4, carb: num(f.n.carb) * 4, fat: num(f.n.fat) * 9 };
  const total = kc.fat + kc.carb + kc.protein;
  const pct = (k) => (total ? Math.round((kc[k] / total) * 100) : 0);
  const parts = [["protein", "蛋白質"], ["carb", "碳水化合物"], ["fat", "脂肪"]];
  const R = 70, C = 2 * Math.PI * R;
  let offset = 0;
  const arcs = total
    ? parts.map(([k]) => {
        const len = (kc[k] / total) * C;
        const arc = `<circle r="${R}" cx="90" cy="90" fill="none" stroke="var(--${k})" stroke-width="20"
          stroke-dasharray="${len} ${C - len}" stroke-dashoffset="${-offset}" transform="rotate(-90 90 90)"/>`;
        offset += len;
        return arc;
      }).join("")
    : "";
  return `
    <div class="ring">
      <svg viewBox="0 0 180 180" role="img" aria-label="卡路里來源分佈">
        <circle r="${R}" cx="90" cy="90" fill="none" stroke="var(--track)" stroke-width="20"/>${arcs}
        <text x="90" y="92" text-anchor="middle" font-size="34" font-weight="900" fill="var(--ink)" letter-spacing="-1">${fmt(f.n.energy, factor)}</text>
        <text x="90" y="114" text-anchor="middle" font-size="13" font-weight="600" fill="var(--ink-3)">kcal</text>
      </svg>
    </div>
    <div class="bars">${parts.map(([k, name]) => `
      <div class="bar-row">
        <div class="top"><span class="nm">${name}</span><span class="v">${pct(k)}%<small>${fmt(f.n[k], factor)} g</small></span></div>
        <div class="bar"><i style="width:${pct(k)}%;background:var(--${k})"></i></div>
      </div>`).join("")}
    </div>
    <p class="note">熱量佔比：1克蛋白質 = 4 kcal、1克碳水化合物 = 4 kcal、1克脂肪 = 9 kcal</p>`;
}

function label(f, factor, servingText) {
  const n = f.n;
  const row = (k, name, unit, cls = "") => `<tr class="${cls}"><td>${name}</td><td>${fmt(n[k], factor)}${typeof n[k] === "number" ? " " + unit : ""}</td></tr>`;
  const mineral = (k, name) => row(k, name, "mg");
  return `
    <div class="label">
      <h3>營養標籤</h3>
      <div class="per">每份食用分量：<b>${esc(servingText)}</b></div>
      <table>
        ${row("energy", "能量", "kcal", "major")}
        ${row("protein", "蛋白質", "g", "major")}
        ${row("fat", "總脂肪", "g", "major")}
        ${row("satfat", "飽和脂肪", "g", "sub")}
        ${row("transfat", "反式脂肪", "g", "sub")}
        ${row("chol", "膽固醇", "mg")}
        ${row("carb", f.carbTotal ? "碳水化合物 (總量)" : "碳水化合物", "g", "major")}
        ${row("sugar", "糖", "g", "sub")}
        ${row("fibre", "膳食纖維", "g", "sub")}
        ${row("sodium", "鈉", "mg", "major")}
        <tr class="sec"><td colspan="2">礦物質和維他命</td></tr>
        ${mineral("potassium", "鉀")}${mineral("calcium", "鈣")}${mineral("magnesium", "鎂")}
        ${mineral("phosphorus", "磷")}${mineral("iron", "鐵")}${mineral("zinc", "鋅")}
        ${mineral("copper", "銅")}${mineral("manganese", "錳")}${mineral("vitc", "維他命C")}
      </table>
    </div>
    <p class="src">「—」表示沒有資料。</p>`;
}

function food(id) {
  const f = BY_ID[id];
  if (!f) return notFound();
  const g = GROUPS[f.g];
  const sub = g.subs[f.s];
  setActiveGroup(f.g);
  document.title = `${f.zh} 營養及卡路里 - 食物營養資料庫`;

  const servings = [{ key: "100", text: "100克", g: 100 }];
  if (f.ref && f.ref.g !== 100) servings.push({ key: "ref", text: `${f.ref.zh} (${f.ref.g}${f.ref.unit === "ml" ? "毫升" : "克"})`, g: f.ref.g });

  const related = DB.foods.filter((x) => x.g === f.g && x.s === f.s && x.id !== f.id);
  // closest calorie matches first, so the list is "similar foods" rather than alphabetical noise
  related.sort((a, b) => Math.abs(num(a.n.energy) - num(f.n.energy)) - Math.abs(num(b.n.energy) - num(f.n.energy)));

  app.innerHTML = `<div class="food-page">
    ${crumbs([["首頁", "#/"], [g.zh, `#/g/${g.id}`], [sub.zh, `#/g/${g.id}/${sub.id}`], [f.zh, ""]])}
    <section class="card">
      <div class="food-head">
        <div>
          <h1>${esc(f.zh)}</h1>
          <div class="en">${esc(f.en)}</div>
          <div class="chips">
            ${f.alias ? f.alias.split("、").map((a) => `<span class="pill soft">又名 ${esc(a.replace(/[\[\]]/g, ""))}</span>`).join("") : ""}
          </div>
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
    <section class="card"><div class="section-head"><h2>相關食物</h2><span class="eyebrow">${esc(sub.zh)}</span></div>
      <ul class="list">${related.slice(0, 8).map((x) => foodRow(x, null)).join("") || '<li class="muted">沒有相關食物</li>'}</ul>
    </section></div>`;

  const render = (grams, text) => {
    const factor = grams / 100;
    document.getElementById("kcalCard").innerHTML = `
      <div><span class="eyebrow">每${esc(text)}</span><div class="big">${fmt(f.n.energy, factor)}<small>kcal</small></div></div>
      <div class="pcf">${[["protein", "蛋白質"], ["carb", "碳水化合物"], ["fat", "脂肪"]].map(([k, l]) =>
        `<div><b>${fmt(f.n[k], factor)}${typeof f.n[k] === "number" ? " g" : ""}</b><span>${l}</span></div>`).join("")}</div>`;
    document.getElementById("macros").innerHTML = macros(f, factor);
    document.getElementById("label").innerHTML = label(f, factor, text);
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

function search(term) {
  setActiveGroup(null);
  const t = term.trim().toLowerCase();
  document.title = `搜尋「${term}」 - 食物營養資料庫`;
  if (q.value !== term) q.value = term;
  const scored = [];
  for (const f of DB.foods) {
    const zh = f.zh.toLowerCase(), en = f.en.toLowerCase(), al = f.alias.toLowerCase();
    let s = -1;
    if (zh === t || en === t) s = 0;
    else if (zh.startsWith(t) || en.startsWith(t)) s = 1;
    else if (zh.includes(t) || al.includes(t)) s = 2;
    else if (en.includes(t)) s = 3;
    if (s >= 0) scored.push([s, zh.length, f]);
  }
  scored.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  app.innerHTML = `
    ${crumbs([["首頁", "#/"], ["搜尋", ""]])}
    <h1 class="page">搜尋「${esc(term)}」</h1>
    <p class="muted">找到 ${scored.length} 種食物</p>
    <div class="card"><ul class="list">${scored.slice(0, 200).map(([, , f]) => foodRow(f, ` · ${esc(GROUPS[f.g].zh)}`)).join("") ||
      '<li class="muted">很抱歉，找不到符合的食物。</li>'}</ul></div>`;
}

function notFound() {
  app.innerHTML = `<p>找不到此頁。<a href="#/">返回首頁</a></p>`;
}

function route() {
  document.body.classList.toggle("is-home", !/^#\/(f|g|search)\//.test(location.hash));
  const parts = location.hash.replace(/^#\/?/, "").split("/").map(decodeURIComponent);
  if (parts[0] === "f") food(parts[1]);
  else if (parts[0] === "g") group(parts[1], parts[2]);
  else if (parts[0] === "search" && parts[1]) search(parts[1]);
  else home();
}

// ---------- boot ----------

let searchTimer;
q.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    const v = q.value.trim();
    location.hash = v ? `#/search/${encodeURIComponent(v)}` : "#/";
  }, 200);
});
document.getElementById("searchForm").addEventListener("submit", (e) => e.preventDefault());

fetch("foods.json")
  .then((r) => r.json())
  .then((data) => {
    DB = data;
    BY_ID = Object.fromEntries(DB.foods.map((f) => [f.id, f]));
    GROUPS = Object.fromEntries(DB.groups.map((g) => [g.id, g]));
    document.getElementById("groupbar").innerHTML = DB.groups
      .map((g) => `<a href="#/g/${g.id}" data-g="${g.id}">${esc(g.zh)}</a>`).join("");
    window.addEventListener("hashchange", route);
    route();
  })
  .catch(() => { app.innerHTML = '<p>無法載入資料。請用本地伺服器開啟（python3 -m http.server）。</p>'; });
