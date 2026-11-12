// GET /api/search?q=<text>&limit=<n>
// Matches foods.search_text (names in all languages + synonyms) of every record and returns
// one row per food group (cluster). The row shown is the best-matching record of the group
// (so "伏特加" shows vodka, not the whiskey record that shares its group), preferring the
// group's main record when it matches equally well.
// Rank: 0 exact name, 1 name starts with q (for Latin-letter queries 0 and 1 are one tier,
// because English names such as "Apple" are too generic to win alone), 2 Chinese / local /
// alias contains q, 3 English contains q, 4 synonym or group match only.
// Ties: Chinese name first, HK (CFS) records, groups with data from more sources, shorter names.
import { json, bad, likeEscape, keyNutrientCols, cached } from "../_lib.js";

async function handle({ request, env }) {
  const url = new URL(request.url);
  const q = (url.searchParams.get("q") || "").trim();
  const limit = Math.min(Math.max(parseInt(url.searchParams.get("limit") || "50", 10) || 50, 1), 200);
  if (!q) return bad("q is required");
  if (q.length > 60) return bad("q is too long");

  const e = likeEscape(q);
  const prefix = `${e}%`, contains = `%${e}%`;
  const latin = /^[\x20-\x7e]+$/.test(q) ? 1 : 0;
  // Queries of 3+ characters use the trigram index search_fts (reads only matching rows);
  // shorter queries (e.g. 白飯) scan foods.search_text, and their answers are cached for a day.
  const useFts = [...q].length >= 3;
  const ftsQuery = '"' + q.replace(/"/g, '""') + '"';
  const candidates = useFts
    ? "id IN (SELECT food_id FROM search_fts WHERE search_fts MATCH ?6)"
    : "search_text LIKE ?3 ESCAPE '\\'";
  const ranked = `
    SELECT id, cluster_id, is_primary, source_id, CASE
      WHEN display_zh = ?1 OR name_zh = ?1 OR display_en = ?1 COLLATE NOCASE OR name_en = ?1 COLLATE NOCASE THEN ?5
      WHEN display_zh LIKE ?2 ESCAPE '\\' OR name_zh LIKE ?2 ESCAPE '\\' OR display_en LIKE ?2 ESCAPE '\\'
           OR name_en LIKE ?2 ESCAPE '\\' THEN 1
      WHEN display_zh LIKE ?3 ESCAPE '\\' OR name_zh LIKE ?3 ESCAPE '\\' OR name_local LIKE ?3 ESCAPE '\\'
           OR alias LIKE ?3 ESCAPE '\\' THEN 2
      WHEN display_en LIKE ?3 ESCAPE '\\' OR name_en LIKE ?3 ESCAPE '\\' THEN 3
      ELSE 4 END AS rank
    FROM foods WHERE ${candidates}`;
  const best = `
    SELECT *, ROW_NUMBER() OVER (PARTITION BY cluster_id
      ORDER BY rank, is_primary DESC, (source_id <> 'cfs'), id) AS pick
    FROM (${ranked})`;

  const db = env.DB;
  const [rows, total] = await db.batch([
    db.prepare(`WITH best AS (${best})
      SELECT p.id, p.display_zh, p.display_en, p.name_local, p.name_en, p.source_id, p.group_zh, p.group_en, b.rank,
             (SELECT COUNT(DISTINCT m.source_id) FROM foods m WHERE m.cluster_id = p.cluster_id) AS n_sources,
             ${keyNutrientCols("p")}
      FROM best b JOIN foods p ON p.id = b.id
      WHERE b.pick = 1
      ORDER BY b.rank, (p.display_zh IS NULL), (p.source_id <> 'cfs'), n_sources DESC,
               length(coalesce(p.display_zh, p.display_en)), p.id
      LIMIT ?4`).bind(q, prefix, contains, limit, latin, ...(useFts ? [ftsQuery] : [])),
    db.prepare(`SELECT COUNT(DISTINCT cluster_id) AS n FROM foods WHERE ${candidates.replace("?6", "?1").replace("?3", "?1")}`)
      .bind(useFts ? ftsQuery : contains),
  ]);
  return json({ q, total: total.results[0].n, results: rows.results }, useFts ? 3600 : 86400);
}

export const onRequestGet = (context) => cached(context, handle);
