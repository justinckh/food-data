// GET /api/foods?ids=<id>,<id>,...   (max 24) - list rows for given foods, e.g. home page picks.
// Ids without a source prefix are taken as CFS ids.
import { json, bad, keyNutrientCols, cached } from "../_lib.js";

async function handle({ request, env }) {
  const ids = (new URL(request.url).searchParams.get("ids") || "")
    .split(",").map((s) => s.trim()).filter(Boolean).slice(0, 24)
    .map((id) => (id.includes(":") ? id : `cfs:${id}`));
  if (!ids.length) return bad("ids is required");
  const rows = await env.DB.prepare(`SELECT f.id, f.display_zh, f.display_en, f.name_local, f.name_en, f.source_id, ${keyNutrientCols("f")}
      FROM foods f WHERE f.id IN (${ids.map((_, i) => `?${i + 1}`).join(",")})`).bind(...ids).all();
  const byId = new Map(rows.results.map((r) => [r.id, r]));
  return json({ results: ids.map((id) => byId.get(id)).filter(Boolean) }, 3600);
}

export const onRequestGet = (context) => cached(context, handle);
