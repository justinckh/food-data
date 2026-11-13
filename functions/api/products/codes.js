// GET /api/products/codes?codes=<barcode>,<barcode>,...   (at most 40)
// Short data (list columns) for a fixed list of products, in the order given. Used for the
// hand-picked products on the products home page. Unknown barcodes are left out.
import { json, bad, cached } from "../../_lib.js";
import { pdb, listCols } from "../../_products.js";

async function handle({ request, env }) {
  const codes = (new URL(request.url).searchParams.get("codes") || "").split(",").map((c) => c.trim()).filter((c) => /^\d{6,14}$/.test(c));
  if (!codes.length) return bad("codes is required");
  if (codes.length > 40) return bad("at most 40 codes");
  const rows = await pdb(env).prepare(`SELECT ${listCols("p")} FROM products p WHERE p.code IN (SELECT value FROM json_each(?1))`)
    .bind(JSON.stringify(codes)).all();
  const byCode = new Map(rows.results.map((r) => [r.code, r]));
  return json({ results: codes.map((c) => byCode.get(c)).filter(Boolean) }, 3600);
}

export const onRequestGet = (context) => cached(context, handle);
