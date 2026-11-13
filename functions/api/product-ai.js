// GET /api/product-ai?code=<barcode>
// AI health score (0-100) and a short analysis of one packaged product, written by DeepSeek in
// Hong Kong Traditional Chinese. The product page loads it automatically.
// Each answer is saved in the table product_ai (one row per product and AI_VERSION), so a product
// calls DeepSeek only once; later views read the saved row. The edge cache sits in front of that.
//
// Secret: DEEPSEEK_API_KEY  (Cloudflare Pages secret; for `npm run dev` put it in .dev.vars)
// Optional variable: DEEPSEEK_MODEL (default deepseek-flash)
import { json, bad, cached } from "../_lib.js";
import { pdb, barcodeVariants, getProduct } from "../_products.js";

// Change this when the prompt changes, so cached answers made with the old prompt are not used.
const AI_VERSION = "1";
const MAX_AGE = 30 * 86400;

const SYSTEM = `你是香港的註冊營養師，為一般市民評估包裝食品是否健康。
根據提供的營養標籤（每100克或100毫升）、成分、Nutri-Score 及 NOVA 加工程度，給出 0 至 100 的健康分數：
90-100 非常健康，可經常食用；70-89 健康；50-69 一般，適量食用；30-49 不太健康，少吃為妙；0-29 不健康，盡量避免。
評分時要考慮食物類別（例如食油、芝士本身脂肪高，飲品要看糖分），並參考香港食物安全中心的「三低」標準：
高糖 >15克/100克（飲品 >7.5克/100毫升），高脂 >20克/100克，高鈉 >600毫克/100克。
資料不足時要說明，並給較保守的分數。不要給醫療建議，不要提及品牌是好是壞。
全部用香港繁體中文（書面語）。只輸出 json，格式如下：
{"score": 62, "verdict": "適量食用", "summary": "不超過80字的總結", "good": ["優點，每點不超過25字"], "watch": ["要注意的地方，每點不超過25字"], "tip": "一句實用建議，不超過40字", "confidence": "high"}
good 和 watch 各 0 至 3 點。confidence 是 high、medium 或 low（資料不足時用 low）。`;

const fmt = (v, unit) => (typeof v === "number" ? `${+v.toFixed(2)} ${unit}` : null);

function describe(p) {
  const n = p.nutrients || {};
  const rows = [
    ["能量", fmt(n.energy_kcal, "kcal")], ["蛋白質", fmt(n.protein, "g")], ["總脂肪", fmt(n.fat, "g")],
    ["飽和脂肪", fmt(n.fat_sat, "g")], ["反式脂肪", fmt(n.fat_trans, "g")], ["碳水化合物", fmt(n.carbohydrate, "g")],
    ["糖", fmt(n.sugars, "g")], ["膳食纖維", fmt(n.fibre, "g")], ["鈉", fmt(n.sodium, "mg")],
  ].filter(([, v]) => v);
  return [
    `產品：${p.name}${p.brand ? `（品牌：${p.brand}）` : ""}${p.quantity ? `，${p.quantity}` : ""}`,
    p.off_category || p.category ? `類別：${p.off_category || p.category}` : null,
    rows.length ? `營養標籤（每100克/毫升）：${rows.map(([k, v]) => `${k} ${v}`).join("、")}` : "營養標籤：沒有資料",
    p.serving_size ? `每份：${p.serving_size}` : null,
    p.nutriscore ? `Nutri-Score：${p.nutriscore.toUpperCase()}` : null,
    p.nova ? `NOVA 加工程度：${p.nova}` : null,
    p.ingredients ? `成分：${p.ingredients.slice(0, 1500)}` : "成分：沒有資料",
    p.allergens ? `致敏物：${p.allergens}` : null,
  ].filter(Boolean).join("\n");
}

async function askDeepSeek(env, text) {
  const res = await fetch("https://api.deepseek.com/chat/completions", {
    method: "POST",
    headers: { "content-type": "application/json", authorization: `Bearer ${env.DEEPSEEK_API_KEY}` },
    body: JSON.stringify({
      model: env.DEEPSEEK_MODEL || "deepseek-flash",
      messages: [{ role: "system", content: SYSTEM }, { role: "user", content: text }],
      response_format: { type: "json_object" },
      temperature: 0.3,
      max_tokens: 800,
    }),
  });
  if (!res.ok) throw Object.assign(new Error(`DeepSeek HTTP ${res.status}`), { status: res.status });
  const d = await res.json();
  const content = (d.choices?.[0]?.message?.content || "").trim();
  return content ? JSON.parse(content) : null;   // blank content = the model could not make valid JSON
}

// Saved answers. Not part of the product build (pipeline/build_products.py), so a product reload
// keeps them. Created on first use.
let tableReady = false;
async function savedTable(db) {
  if (!tableReady) {
    await db.prepare(`CREATE TABLE IF NOT EXISTS product_ai (code TEXT NOT NULL, ai_version TEXT NOT NULL,
      result TEXT NOT NULL, created TEXT NOT NULL, PRIMARY KEY (code, ai_version)) WITHOUT ROWID`).run();
    tableReady = true;
  }
}

const str = (s, n) => (typeof s === "string" ? s.trim().slice(0, n) : "");
const list = (a) => (Array.isArray(a) ? a.map((s) => str(s, 60)).filter(Boolean).slice(0, 3) : []);

async function handle({ request, env }) {
  const code = new URL(request.url).searchParams.get("code");
  if (!barcodeVariants(code).length) return bad("code must be a barcode (6-14 digits)");
  if (!env.DEEPSEEK_API_KEY) return bad("AI is not set up (DEEPSEEK_API_KEY is missing)", 503);
  const found = await getProduct(env, code);
  if (!found) return bad("product not found", 404);
  const p = found.product;
  const db = pdb(env);
  await savedTable(db);
  const saved = await db.prepare("SELECT result FROM product_ai WHERE code = ?1 AND ai_version = ?2")
    .bind(p.code, AI_VERSION).first();
  if (saved) return json(JSON.parse(saved.result), MAX_AGE);
  if (!p.has_nutrition && !p.ingredients) return bad("not enough data for an analysis", 422);

  let out = null;
  for (let i = 0; i < 2 && !out; i++) {   // one retry for a blank / invalid JSON answer
    try {
      out = await askDeepSeek(env, describe(p));
    } catch (e) {
      if (e.status) return bad("AI service error", 502);   // HTTP error from DeepSeek: do not retry
    }
  }
  const score = Math.round(Number(out?.score));
  if (!out || !(score >= 0 && score <= 100)) return bad("AI answer was not valid", 502);
  const result = {
    code: p.code,
    score,
    verdict: str(out.verdict, 12),
    summary: str(out.summary, 200),
    good: list(out.good),
    watch: list(out.watch),
    tip: str(out.tip, 100),
    confidence: ["high", "medium", "low"].includes(out.confidence) ? out.confidence : "medium",
    model: env.DEEPSEEK_MODEL || "deepseek-flash",
    created: new Date().toISOString().slice(0, 10),
  };
  await db.prepare("INSERT OR REPLACE INTO product_ai (code, ai_version, result, created) VALUES (?1, ?2, ?3, ?4)")
    .bind(p.code, AI_VERSION, JSON.stringify(result), result.created).run();
  return json(result, MAX_AGE);
}

export const onRequestGet = (context) => {
  const url = new URL(context.request.url);
  url.searchParams.set("ai", AI_VERSION);
  return cached({ ...context, request: new Request(url.toString(), context.request) }, handle);
};
