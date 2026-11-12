// GET /api/meta - counts, sources, nutrient list and the shared categories for browsing.
// Counts are stored by pipeline/serve_db.py (sources.foods, categories.n).
import { json, cached } from "../_lib.js";

async function handle({ env }) {
  const db = env.DB;
  const [sources, nutrients, categories] = await db.batch([
    db.prepare(`SELECT id, name, publisher, country, licence, attribution, url, version, foods
                FROM sources ORDER BY foods DESC`),
    db.prepare("SELECT id, name_zh, name_en, unit FROM nutrients ORDER BY sort_order"),
    db.prepare("SELECT id, name_zh, name_en, n, n_records FROM categories ORDER BY sort_order"),
  ]);
  return json({
    foods: sources.results.reduce((n, s) => n + s.foods, 0),
    main_records: categories.results.reduce((n, c) => n + c.n, 0),
    sources: sources.results,
    nutrients: nutrients.results,
    categories: categories.results,
  }, 3600);
}

export const onRequestGet = (context) => cached(context, handle);
