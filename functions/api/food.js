// GET /api/food?id=<food id>   e.g. id=cfs:070100F007661
// Old site ids without a source prefix are taken as CFS ids.
// Returns the record, all its nutrients, servings, its source, the other records of the
// same food group (other countries' values), 'similar' foods, and related foods from the
// same source group. The lists are stored with the food row (pipeline/serve_db.py), so the
// page reads one row per food shown.
import { json, bad, listCols, cached } from "../_lib.js";

const parse = (s, empty) => (s ? JSON.parse(s) : empty);

async function handle({ request, env }) {
  let id = (new URL(request.url).searchParams.get("id") || "").trim();
  if (!id) return bad("id is required");
  if (!id.includes(":")) id = `cfs:${id}`;
  const db = env.DB;

  const food = await db.prepare("SELECT * FROM foods WHERE id = ?1").bind(id).first();
  if (!food) return bad("food not found", 404);

  const byIds = (ids) => db.prepare(`SELECT ${listCols("p")} FROM foods p
      WHERE p.id IN (SELECT value FROM json_each(?1))`).bind(ids || "[]");
  const [nutrientList, source, members, similar, related] = await db.batch([
    db.prepare("SELECT id, name_zh, name_en, unit FROM nutrients ORDER BY sort_order"),
    db.prepare("SELECT id, name, publisher, country, licence, attribution, url, version FROM sources WHERE id = ?1")
      .bind(food.source_id),
    db.prepare(`SELECT m.id, m.source_id, s.country, s.name AS source_name, m.name_zh, m.name_en, m.name_local,
        m.sample_note, m.is_copy, m.links, m.energy_kcal, m.protein, m.fat, m.carbohydrate
      FROM foods m JOIN sources s ON s.id = m.source_id
      WHERE m.id IN (SELECT value FROM json_each(?1)) AND m.id <> ?2
      ORDER BY m.source_id, m.id`).bind(food.members, id),
    byIds(food.similar),
    byIds(food.related),
  ]);

  const values = JSON.parse(food.nutrients);
  const nutrients = nutrientList.results.filter((n) => n.id in values).map((n) => {
    const v = values[n.id];
    return typeof v === "object" && v !== null
      ? { ...n, value: v.v ?? null, flag: v.f ?? null, method: v.m ?? null, estimated: v.e ?? 0 }
      : { ...n, value: v, flag: null, method: null, estimated: 0 };
  });
  const links = parse(food.links, {});
  const inOrder = (rows, ids) => {
    const byId = new Map(rows.results.map((r) => [r.id, r]));
    return parse(ids, []).map((i) => byId.get(i)).filter(Boolean);
  };
  const similarIds = food.similar, relatedIds = food.related;
  const servings = parse(food.servings, []).map(([label_en, label_zh, amount, unit]) => ({ label_en, label_zh, amount, unit }));
  for (const k of ["nutrients", "servings", "members", "links", "similar", "related", "search_text"]) delete food[k];

  return json({
    food,
    nutrients,
    servings,
    source: source.results[0] || null,
    members: members.results.map(({ links: l, ...m }) => ({
      ...m, link_to_this: links[m.id] || parse(l, {})[id] || null,
    })),
    similar: inOrder(similar, similarIds),
    related: inOrder(related, relatedIds),
  }, 3600);
}

export const onRequestGet = (context) => cached(context, handle);
