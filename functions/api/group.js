// GET /api/group?g=<group slug>&s=<subgroup index>&sort=name|kcalAsc|kcalDesc|protein
// Browse the HK (CFS) food groups, the same grouping the site used before.
import { json, bad, slug, keyNutrientCols, cached } from "../_lib.js";

const SORT = {
  name: "display_zh",
  kcalAsc: "coalesce(energy_kcal, 1e9)",
  kcalDesc: "coalesce(energy_kcal, -1) DESC",
  protein: "coalesce(protein, -1) DESC",
};

async function handle({ request, env }) {
  const url = new URL(request.url);
  const g = url.searchParams.get("g") || "";
  const s = url.searchParams.get("s");
  const order = SORT[url.searchParams.get("sort")] || SORT.name;
  const db = env.DB;

  const groups = await db.prepare(`SELECT DISTINCT group_en, subgroup_en FROM foods WHERE source_id = 'cfs'
                                   ORDER BY group_en, subgroup_en`).all();
  const subs = groups.results.filter((r) => slug(r.group_en) === g);
  if (!subs.length) return bad("group not found", 404);
  const groupEn = subs[0].group_en;
  const sub = s === null || s === "" ? null : subs[parseInt(s, 10)];
  if (s && !sub) return bad("subgroup not found", 404);

  const rows = await db.prepare(`SELECT * FROM (
      SELECT f.id, f.display_zh, f.display_en, f.name_local, f.name_en, f.subgroup_zh, f.subgroup_en, ${keyNutrientCols("f")}
      FROM foods f WHERE f.source_id = 'cfs' AND f.group_en = ?1 AND (?2 IS NULL OR f.subgroup_en = ?2))
    ORDER BY ${order}`).bind(groupEn, sub ? sub.subgroup_en : null).all();
  return json({ group: groupEn, subgroup: sub ? sub.subgroup_en : null, results: rows.results }, 3600);
}

export const onRequestGet = (context) => cached(context, handle);
