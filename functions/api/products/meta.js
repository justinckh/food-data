// GET /api/products/meta : product categories and markets with counts, and the totals.
import { json, cached } from "../../_lib.js";
import { pdb, OFF_ATTRIBUTION } from "../../_products.js";

async function handle({ env }) {
  const db = pdb(env);
  const [cats, markets, totals] = await db.batch([
    db.prepare("SELECT id, name_zh, name_en, n FROM product_categories WHERE n > 0 ORDER BY sort_order"),
    db.prepare("SELECT id, name_zh, n FROM product_markets WHERE n > 0 ORDER BY sort_order"),
    db.prepare("SELECT n FROM product_categories"),
  ]);
  const total = totals.results.reduce((s, r) => s + r.n, 0);
  return json({ total, categories: cats.results, markets: markets.results, source: OFF_ATTRIBUTION }, 3600);
}

export const onRequestGet = (context) => cached(context, handle);
