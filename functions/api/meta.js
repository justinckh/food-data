// GET /api/meta - counts, sources, nutrient list and the HK (CFS) food groups for browsing.
import { json, slug, cached } from "../_lib.js";

async function handle({ env }) {
  const db = env.DB;
  const [counts, sources, nutrients, groups] = await db.batch([
    db.prepare("SELECT COUNT(*) AS foods, SUM(is_primary) AS main_records FROM foods"),
    db.prepare(`SELECT s.id, s.name, s.publisher, s.country, s.licence, s.attribution, s.url, s.version,
                       COUNT(f.id) AS foods
                FROM sources s LEFT JOIN foods f ON f.source_id = s.id GROUP BY s.id ORDER BY foods DESC`),
    db.prepare("SELECT id, name_zh, name_en, unit FROM nutrients ORDER BY sort_order"),
    db.prepare(`SELECT group_zh, group_en, subgroup_zh, subgroup_en, COUNT(*) AS n
                FROM foods WHERE source_id = 'cfs' GROUP BY group_en, subgroup_en ORDER BY group_en, subgroup_en`),
  ]);

  const byGroup = new Map();
  for (const r of groups.results) {
    const key = slug(r.group_en);
    if (!byGroup.has(key)) byGroup.set(key, { id: key, zh: r.group_zh, en: r.group_en, subs: [] });
    const g = byGroup.get(key);
    g.subs.push({ id: g.subs.length, zh: r.subgroup_zh, en: r.subgroup_en, n: r.n });
  }

  return json({
    foods: counts.results[0].foods,
    main_records: counts.results[0].main_records,
    sources: sources.results,
    nutrients: nutrients.results,
    groups: [...byGroup.values()],
  }, 3600);
}

export const onRequestGet = (context) => cached(context, handle);
