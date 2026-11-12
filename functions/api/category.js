// GET /api/category?c=<category id | all>&sub=<subcategory id>&src=<source id>&sort=name|kcalAsc|kcalDesc|protein&page=<n>
// Browse the whole database by the shared categories (pipeline/categories.py) and their
// subcategories (pipeline/subcategories.py). c=all browses every food.
// Without src: one row per food group (main records). With src: EVERY record of that source,
// also the records that are shown inside another source's group.
// Counts: n = food groups (main records), n_records = all records; per source = all records.
import { json, bad, listCols, cached } from "../_lib.js";

const PAGE = 60;
const SORT = {
  // Chinese names first, then names that start with Latin letters or digits (e.g. "Quorn素肉塊")
  name: "(display_zh IS NULL), (unicode(display_zh) < 11904), coalesce(display_zh, display_en, name_en, name_local)",
  kcalAsc: "(energy_kcal IS NULL), energy_kcal",
  kcalDesc: "(energy_kcal IS NULL), energy_kcal DESC",
  protein: "(protein IS NULL), protein DESC",
};

async function handle({ request, env }) {
  const url = new URL(request.url);
  const c = url.searchParams.get("c") || "";
  const sub = url.searchParams.get("sub") || null;
  const src = url.searchParams.get("src") || null;
  const sortKey = SORT[url.searchParams.get("sort")] ? url.searchParams.get("sort") : "name";
  const page = Math.max(parseInt(url.searchParams.get("page") || "1", 10) || 1, 1);
  const db = env.DB;
  const all = c === "all";

  let cat;
  if (all) {
    const t = await db.prepare("SELECT SUM(n) AS n, SUM(n_records) AS n_records FROM categories").first();
    cat = { id: "all", name_zh: "全部食物", name_en: "All foods", n: t.n, n_records: t.n_records };
  } else {
    cat = await db.prepare("SELECT id, name_zh, name_en, n, n_records FROM categories WHERE id = ?1").bind(c).first();
    if (!cat) return bad("category not found", 404);
  }
  if (sub && (all || !sub.startsWith(`${c}.`))) return bad("subcategory not found", 404);

  // ?1 category (NULL = all), ?2 subcategory, ?3 source
  const where = "(?1 IS NULL OR f.category = ?1) AND (?2 IS NULL OR f.subcategory = ?2)";
  const cv = all ? null : c;
  const [rows, bySource, subs] = await db.batch([
    db.prepare(`SELECT * FROM (
        SELECT ${listCols("f")}, f.is_primary
        FROM foods f WHERE ${where} AND (CASE WHEN ?3 IS NULL THEN f.is_primary = 1 ELSE f.source_id = ?3 END))
      ORDER BY ${SORT[sortKey]}, id LIMIT ${PAGE} OFFSET ?4`).bind(cv, sub, src, (page - 1) * PAGE),
    db.prepare(`SELECT source_id, COUNT(*) AS n FROM foods f WHERE ${where}
                GROUP BY source_id ORDER BY n DESC`).bind(cv, sub),
    db.prepare(`SELECT id, name_zh, name_en, n, n_records FROM subcategories WHERE category = ?1
                ORDER BY sort_order`).bind(cv),
  ]);
  const subRow = sub ? subs.results.find((s) => s.id === sub) : null;
  if (sub && !subRow) return bad("subcategory not found", 404);
  const records = bySource.results.reduce((n, r) => n + r.n, 0);
  const total = src ? (bySource.results.find((r) => r.source_id === src)?.n || 0) : (subRow ? subRow.n : cat.n);
  return json({
    category: cat, subcategory: subRow, subcategories: subs.results, source: src, sort: sortKey, page,
    page_size: PAGE, total, n_records: records, sources: bySource.results, results: rows.results,
  }, 3600);
}

export const onRequestGet = (context) => cached(context, handle);
