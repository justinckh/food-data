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
