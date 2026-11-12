// GET /api/food?id=<food id>   e.g. id=cfs:070100F007661
// Old site ids without a source prefix are taken as CFS ids.
// Returns the record, all its nutrients, servings, its source, the other records of the
// same food group (other countries' values), 'similar' foods, and related foods from the
// same source group.
import { json, bad, keyNutrientCols, cached } from "../_lib.js";

async function handle({ request, env }) {
  let id = (new URL(request.url).searchParams.get("id") || "").trim();
  if (!id) return bad("id is required");
  if (!id.includes(":")) id = `cfs:${id}`;
  const db = env.DB;

  // one round trip for the record itself, then one batch for everything else
  const food = await db.prepare(`SELECT id, source_id, source_code, display_zh, display_en, name_zh, name_en,
      name_local, alias, group_zh, group_en, subgroup_zh, subgroup_en, description, origin_source,
      cluster_id, is_primary, sample_note, category,
      (SELECT value FROM food_nutrients WHERE food_id = foods.id AND nutrient_id = 'energy_kcal') AS kcal
      FROM foods WHERE id = ?1`).bind(id).first();
  if (!food) return bad("food not found", 404);

  const [nutrients, servings, source, members, similar, related] = await db.batch([
    db.prepare(`SELECT n.id, n.name_zh, n.name_en, n.unit, v.value, v.flag, v.method, v.estimated
      FROM food_nutrients v JOIN nutrients n ON n.id = v.nutrient_id
      WHERE v.food_id = ?1 ORDER BY n.sort_order`).bind(id),
    db.prepare("SELECT label_en, label_zh, amount, unit FROM servings WHERE food_id = ?1 ORDER BY amount").bind(id),
    db.prepare("SELECT id, name, publisher, country, licence, attribution, url, version FROM sources WHERE id = ?1")
      .bind(food.source_id),
    db.prepare(`SELECT m.id, m.source_id, s.country, s.name AS source_name, m.name_zh, m.name_en, m.name_local,
        m.sample_note,
        EXISTS (SELECT 1 FROM food_links c WHERE c.food_id = m.id AND c.match_type = 'exact_copy') AS is_copy,
        (SELECT l.match_type FROM food_links l WHERE (l.food_id = m.id AND l.canonical_id = ?1)
            OR (l.food_id = ?1 AND l.canonical_id = m.id)) AS link_to_this,
        ${keyNutrientCols("m")}
      FROM foods m JOIN sources s ON s.id = m.source_id
      WHERE m.cluster_id = ?2 AND m.id <> ?1
      ORDER BY m.source_id, m.id`).bind(id, food.cluster_id),
    db.prepare(`SELECT DISTINCT p.id, p.display_zh, p.display_en, p.name_local, p.name_en, p.source_id, ${keyNutrientCols("p")}
      FROM food_links l
      JOIN foods a ON a.id IN (l.food_id, l.canonical_id) AND a.cluster_id = ?1
      JOIN foods o ON o.id IN (l.food_id, l.canonical_id) AND o.cluster_id <> ?1
      JOIN foods p ON p.id = o.cluster_id
      WHERE l.match_type = 'similar' LIMIT 8`).bind(food.cluster_id),
    db.prepare(`SELECT p.id, p.display_zh, p.display_en, p.name_local, p.name_en, p.source_id, ${keyNutrientCols("p")}
      FROM foods p WHERE p.source_id = ?1 AND p.is_primary = 1 AND p.id <> ?2
        AND coalesce(p.subgroup_en, p.group_en, '') = coalesce(?3, ?4, '')
      ORDER BY abs(coalesce((SELECT value FROM food_nutrients WHERE food_id = p.id AND nutrient_id = 'energy_kcal'), 0)
                   - coalesce(?5, 0))
      LIMIT 8`).bind(food.source_id, id, food.subgroup_en, food.group_en, food.kcal ?? 0),
  ]);

  delete food.kcal;
  return json({
    food,
    nutrients: nutrients.results,
    servings: servings.results,
    source: source.results[0] || null,
    members: members.results,
    similar: similar.results,
    related: related.results,
  }, 3600);
}

export const onRequestGet = (context) => cached(context, handle);
