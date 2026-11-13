// GET /api/products/search?q=<text or barcode>&limit=<n>
// Digits only (6-14) = a barcode: exact match, then barcodes that start with it.
// Text: product name, brand and Open Food Facts category words. 3+ characters use the trigram
// index products_fts; shorter text scans products.search_text (cached for a day).
// Rank: name equals q, name starts with q, name contains q, brand contains q, other; then popularity.
import { json, bad, likeEscape, cached } from "../../_lib.js";
import { pdb, listCols, barcodeVariants } from "../../_products.js";

async function handle({ request, env }) {
  const url = new URL(request.url);
  const q = (url.searchParams.get("q") || "").trim();
  const limit = Math.min(Math.max(parseInt(url.searchParams.get("limit") || "60", 10) || 60, 1), 200);
  if (!q) return bad("q is required");
  if (q.length > 60) return bad("q is too long");
  const db = pdb(env);

  if (/^\d{6,14}$/.test(q)) {
    const rows = await db.prepare(`SELECT ${listCols("p")} FROM products p
        WHERE p.code IN (SELECT value FROM json_each(?1)) OR p.code LIKE ?2
        ORDER BY (p.code IN (SELECT value FROM json_each(?1))) DESC, p.scans DESC LIMIT ?3`)
      .bind(JSON.stringify(barcodeVariants(q)), `${q}%`, limit).all();
    return json({ q, barcode: true, total: rows.results.length, results: rows.results }, 3600);
  }

  const lq = q.toLowerCase();
  const e = likeEscape(lq);
  const useFts = [...q].length >= 3;
  const candidates = useFts
    ? "p.code IN (SELECT code FROM products_fts WHERE products_fts MATCH ?5)"
    : "p.search_text LIKE ?3 ESCAPE '\\'";
  const ftsArg = useFts ? ['"' + lq.replace(/"/g, '""') + '"'] : [];
  const [rows, total] = await db.batch([
    db.prepare(`SELECT ${listCols("p")} FROM products p WHERE ${candidates}
      ORDER BY CASE WHEN lower(p.name) = ?1 THEN 0 WHEN lower(p.name) LIKE ?2 ESCAPE '\\' THEN 1
        WHEN lower(p.name) LIKE ?3 ESCAPE '\\' THEN 2 WHEN lower(p.brand) LIKE ?3 ESCAPE '\\' THEN 3 ELSE 4 END,
        p.has_nutrition DESC, p.scans DESC, length(p.name)
      LIMIT ?4`).bind(lq, `${e}%`, `%${e}%`, limit, ...ftsArg),
    useFts
      ? db.prepare("SELECT COUNT(*) AS n FROM products_fts WHERE products_fts MATCH ?1").bind(ftsArg[0])
      : db.prepare("SELECT COUNT(*) AS n FROM products p WHERE p.search_text LIKE ?1 ESCAPE '\\'").bind(`%${e}%`),
  ]);
  return json({ q, barcode: false, total: total.results[0].n, results: rows.results }, useFts ? 3600 : 86400);
}

export const onRequestGet = (context) => cached(context, handle);
