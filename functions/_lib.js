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

// Columns of a food list row (search results, category pages, related foods).
// Key nutrients are normal columns of foods (pipeline/serve_db.py KEY_NUTRIENTS).
export function listCols(a) {
  return ["id", "display_zh", "display_en", "name_local", "name_en", "source_id", "n_sources",
    "energy_kcal", "protein", "fat", "carbohydrate"].map((c) => `${a}.${c}`).join(", ");
}

// Serve GET responses from Cloudflare's edge cache when possible. The data only changes
// when the database is reloaded (see PROJECT.md 4.4), so answers are cached for an hour.
// DATA_VERSION is part of the cache key: change it after each reload to drop old answers.
export const DATA_VERSION = "2026-11-13d";

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
