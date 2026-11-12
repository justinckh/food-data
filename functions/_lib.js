// Shared helpers for the API (Cloudflare Pages Functions + D1 binding "DB").

export function json(data, maxAge = 300, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": `public, max-age=${maxAge}`,
    },
  });
}

export const bad = (msg, status = 400) => json({ error: msg }, 0, status);

// LIKE pattern with % and _ escaped (queries use ESCAPE '\')
export const likeEscape = (s) => s.replace(/[\\%_]/g, (c) => "\\" + c);

export function slug(s) {
  return String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

// Key nutrients for list rows, as one sub-select per nutrient (alias.food id column given).
export function keyNutrientCols(alias) {
  return ["energy_kcal", "protein", "fat", "carbohydrate"]
    .map((n) => `(SELECT value FROM food_nutrients WHERE food_id = ${alias}.id AND nutrient_id = '${n}') AS ${n}`)
    .join(", ");
}

// Serve GET responses from Cloudflare's edge cache when possible. The data only changes
// when the database is reloaded (see PROJECT.md 4.4), so answers are cached for an hour.
// DATA_VERSION is part of the cache key: change it after each reload to drop old answers.
export const DATA_VERSION = "2026-11-12a";

export async function cached(context, handler) {
  const url = new URL(context.request.url);
  url.searchParams.set("_v", DATA_VERSION);
  const key = new Request(url.toString(), { method: "GET" });
  const cache = caches.default;
  const hit = await cache.match(key);
  if (hit) return hit;
  const res = await handler(context);
  if (res.status === 200) context.waitUntil(cache.put(key, res.clone()));
  return res;
}
