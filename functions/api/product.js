// GET /api/product?code=<barcode>
// One packaged product: label nutrients per 100 g, serving size, ingredients, allergens, and more
// products of the same brand. If the barcode is not in our database (we store products sold in Asian
// markets only), the product is looked up live on Open Food Facts ("live": true).
import { json, bad, cached } from "../_lib.js";
import { pdb, listCols, barcodeVariants, getProduct, OFF_ATTRIBUTION } from "../_products.js";

async function handle({ request, env }) {
  const code = new URL(request.url).searchParams.get("code");
  if (!barcodeVariants(code).length) return bad("code must be a barcode (6-14 digits)");
  const found = await getProduct(env, code);
  if (!found) return bad("product not found", 404);
  const { product, live } = found;
  const sameBrand = !live && product.brand
    ? (await pdb(env).prepare(`SELECT ${listCols("p")} FROM products p WHERE p.brand = ?1 AND p.code <> ?2
        ORDER BY p.has_nutrition DESC, p.scans DESC LIMIT 8`).bind(product.brand, product.code).all()).results
    : [];
  return json({ product, live, same_brand: sameBrand, source: OFF_ATTRIBUTION }, live ? 86400 : 3600);
}

export const onRequestGet = (context) => cached(context, handle);
