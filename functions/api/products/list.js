// GET /api/products/list?c=<category | all>&m=<market code>&sort=<popular|name|kcalAsc|kcalDesc|protein>&page=<n>
// Products of one category (or all), optionally only those sold in one market. 40 per page.
import { json, bad, cached } from "../../_lib.js";
import { pdb, listCols } from "../../_products.js";

const PAGE = 40;
const SORTS = {
  popular: "p.has_nutrition DESC, p.scans DESC, p.code",
  name: "p.name COLLATE NOCASE, p.code",
  kcalAsc: "p.energy_kcal IS NULL, p.energy_kcal, p.code",
  kcalDesc: "p.energy_kcal IS NULL, p.energy_kcal DESC, p.code",
  protein: "p.protein IS NULL, p.protein DESC, p.code",
};

async function handle({ request, env }) {
  const url = new URL(request.url);
  const c = url.searchParams.get("c") || "all";
  const m = (url.searchParams.get("m") || "").toUpperCase();
  const sort = SORTS[url.searchParams.get("sort")] ? url.searchParams.get("sort") : "popular";
  const page = Math.max(parseInt(url.searchParams.get("page") || "1", 10) || 1, 1);
  if (m && !/^[A-Z]{2}$/.test(m)) return bad("m must be a market code");
  const db = pdb(env);

  const where = [], args = [];
  if (c !== "all") { args.push(c); where.push(`p.category = ?${args.length}`); }
  if (m) { args.push(`%,${m},%`); where.push(`p.markets LIKE ?${args.length}`); }
  const w = where.length ? `WHERE ${where.join(" AND ")}` : "";
  const [rows, total, cat] = await db.batch([
    db.prepare(`SELECT ${listCols("p")} FROM products p ${w} ORDER BY ${SORTS[sort]} LIMIT ${PAGE} OFFSET ${(page - 1) * PAGE}`).bind(...args),
    db.prepare(`SELECT COUNT(*) AS n FROM products p ${w}`).bind(...args),
    db.prepare("SELECT id, name_zh, name_en, n FROM product_categories WHERE id = ?1").bind(c),
  ]);
  if (c !== "all" && !cat.results.length) return bad("category not found", 404);
  return json({
    category: cat.results[0] || { id: "all", name_zh: "全部包裝食品", name_en: "All products" },
    market: m || null, sort, page, page_size: PAGE, total: total.results[0].n, results: rows.results,
  }, 3600);
}

export const onRequestGet = (context) => cached(context, handle);
