// GET /api/category?c=<category id>&src=<source id>&sort=name|kcalAsc|kcalDesc|protein&page=<n>
// Browse the whole database by the shared categories (pipeline/categories.py).
// Shows one row per food group (main records only). 60 rows per page.
// Returns per-source counts for the filter chips.
import { json, bad, listCols, cached } from "../_lib.js";

const PAGE = 60;
const SORT = {
  name: "(display_zh IS NULL), coalesce(display_zh, display_en, name_en, name_local)",
  kcalAsc: "(energy_kcal IS NULL), energy_kcal",
  kcalDesc: "(energy_kcal IS NULL), energy_kcal DESC",
  protein: "(protein IS NULL), protein DESC",
};

async function handle({ request, env }) {
  const url = new URL(request.url);
  const c = url.searchParams.get("c") || "";
  const src = url.searchParams.get("src") || null;
  const sortKey = SORT[url.searchParams.get("sort")] ? url.searchParams.get("sort") : "name";
  const page = Math.max(parseInt(url.searchParams.get("page") || "1", 10) || 1, 1);
  const db = env.DB;

  const cat = await db.prepare("SELECT id, name_zh, name_en FROM categories WHERE id = ?1").bind(c).first();
  if (!cat) return bad("category not found", 404);

  const [rows, bySource] = await db.batch([
    db.prepare(`SELECT * FROM (
        SELECT ${listCols("f")}
        FROM foods f WHERE f.category = ?1 AND f.is_primary = 1 AND (?2 IS NULL OR f.source_id = ?2))
      ORDER BY ${SORT[sortKey]}, id LIMIT ${PAGE} OFFSET ?3`).bind(c, src, (page - 1) * PAGE),
    db.prepare(`SELECT source_id, COUNT(*) AS n FROM foods WHERE category = ?1 AND is_primary = 1
                GROUP BY source_id ORDER BY n DESC`).bind(c),
  ]);
  const total = bySource.results.reduce((n, r) => n + (!src || r.source_id === src ? r.n : 0), 0);
  return json({
    category: cat, source: src, sort: sortKey, page, page_size: PAGE, total,
    sources: bySource.results, results: rows.results,
  }, 3600);
}

export const onRequestGet = (context) => cached(context, handle);
