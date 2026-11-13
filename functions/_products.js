// Shared helpers for the packaged-food products API (Open Food Facts data, pipeline/build_products.py).
// Products live in the tables products / products_fts / product_categories / product_markets.
// Binding: PRODUCTS if it is set (a separate D1 database), else DB (the same database as the foods).

export const pdb = (env) => env.PRODUCTS || env.DB;

export const OFF_ATTRIBUTION = {
  name: "Open Food Facts",
  url: "https://world.openfoodfacts.org",
  licence: "ODbL 1.0 (資料庫) · DbCL 1.0 (內容) · CC BY-SA (相片)",
  note: "資料由 Open Food Facts 用戶根據包裝標籤輸入，可能有錯漏，請以包裝為準。",
};

export const PRODUCT_LIST_COLS = ["code", "name", "brand", "quantity", "category", "image", "nutriscore",
  "energy_kcal", "protein", "fat", "carbohydrate", "has_nutrition"];
export const listCols = (a = "p") => PRODUCT_LIST_COLS.map((c) => `${a}.${c}`).join(", ");

// Barcodes: digits only, 6-14 long. EAN-13 / UPC-A codes may be stored with or without a leading 0.
export function barcodeVariants(code) {
  const c = String(code || "").replace(/\D/g, "");
  if (c.length < 6 || c.length > 14) return [];
  const out = new Set([c, c.replace(/^0+/, "")]);
  if (c.length === 12) out.add("0" + c);
  if (c.length === 13 && c.startsWith("0")) out.add(c.slice(1));
  return [...out].filter(Boolean);
}

// ----- live lookup (barcode not in our database) -----

// OFF nutriment key -> [our nutrient id, factor]; same table as pipeline/build_products.py NUTRIENT_MAP
const NUTRIENT_MAP = {
  "energy-kcal_100g": ["energy_kcal", 1], "energy-kj_100g": ["energy_kj", 1],
  proteins_100g: ["protein", 1], carbohydrates_100g: ["carbohydrate", 1], fat_100g: ["fat", 1],
  "saturated-fat_100g": ["fat_sat", 1], "trans-fat_100g": ["fat_trans", 1],
  "monounsaturated-fat_100g": ["fat_mono", 1], "polyunsaturated-fat_100g": ["fat_poly", 1],
  cholesterol_100g: ["cholesterol", 1e3], fiber_100g: ["fibre", 1], sugars_100g: ["sugars", 1],
  sodium_100g: ["sodium", 1e3], salt_100g: ["salt_eq", 1],
  potassium_100g: ["potassium", 1e3], calcium_100g: ["calcium", 1e3], magnesium_100g: ["magnesium", 1e3],
  phosphorus_100g: ["phosphorus", 1e3], iron_100g: ["iron", 1e3], zinc_100g: ["zinc", 1e3],
  "vitamin-c_100g": ["vitamin_c", 1e3], "vitamin-a_100g": ["vitamin_a_re", 1e6], "vitamin-d_100g": ["vitamin_d", 1e6],
  "vitamin-b1_100g": ["vitamin_b1", 1e3], "vitamin-b2_100g": ["vitamin_b2", 1e3], "vitamin-b12_100g": ["vitamin_b12", 1e6],
  caffeine_100g: ["caffeine", 1e3],
};
const GRAM_IDS = new Set(["protein", "carbohydrate", "fat", "fat_sat", "fat_trans", "fat_mono", "fat_poly", "fibre", "sugars", "salt_eq"]);

const FIELDS = ["code", "product_name", "product_name_zh", "product_name_zh-hant", "product_name_en", "generic_name",
  "brands", "quantity", "main_category", "categories_tags", "countries", "image_small_url", "image_front_small_url",
  "nutriscore_grade", "nova_group", "serving_size", "serving_quantity", "nutriments", "ingredients_text",
  "allergens_tags", "traces_tags", "labels", "last_modified_t"].join(",");

const tagText = (tags) => (tags || []).filter(Boolean).map((t) => t.replace(/^[a-z]{2}:/, "").replace(/-/g, " ")).join(", ") || null;

export async function lookupLive(code) {
  const url = `https://world.openfoodfacts.org/api/v2/product/${encodeURIComponent(code)}.json?fields=${FIELDS}`;
  const res = await fetch(url, {
    headers: { "user-agent": "FoodNutritionSite/1.0 (product lookup)" },
    cf: { cacheTtl: 86400, cacheEverything: true },
  });
  if (res.status === 404) return null;
  if (!res.ok) throw Object.assign(new Error(`Open Food Facts HTTP ${res.status}`), { status: 502 });
  const d = await res.json();
  if (d.status !== 1 || !d.product) return null;
  const p = d.product, nm = p.nutriments || {};
  const nutrients = {};
  for (const [k, [id, f]] of Object.entries(NUTRIENT_MAP)) {
    const v = typeof nm[k] === "number" ? nm[k] : parseFloat(nm[k]);
    if (!(v >= 0)) continue;
    const x = v * f;
    if (GRAM_IDS.has(id) && x > 100) continue;
    nutrients[id] = +x.toFixed(x < 1 ? 4 : 2);
  }
  if (nutrients.energy_kcal === undefined && nutrients.energy_kj !== undefined) nutrients.energy_kcal = +(nutrients.energy_kj / 4.184).toFixed(1);
  const name = p["product_name_zh-hant"] || p.product_name_zh || p.product_name || p.product_name_en || p.generic_name;
  if (!name && !Object.keys(nutrients).length) return null;
  return {
    code: p.code || code, name: name || code, generic_name: p.generic_name || null,
    brand: (p.brands || "").split(",")[0].trim() || null, quantity: p.quantity || null,
    category: null, off_category: tagText([p.main_category]),
    markets: "", countries: p.countries || null,
    image: p.image_front_small_url || p.image_small_url || null,
    nutriscore: /^[a-e]$/.test(p.nutriscore_grade || "") ? p.nutriscore_grade : null,
    nova: [1, 2, 3, 4].includes(+p.nova_group) ? +p.nova_group : null,
    serving_size: p.serving_size || null, serving_g: parseFloat(p.serving_quantity) || null,
    nutrients, has_nutrition: ["energy_kcal", "protein", "fat", "carbohydrate"].some((k) => k in nutrients) ? 1 : 0,
    ingredients: p.ingredients_text || null, allergens: tagText(p.allergens_tags), traces: tagText(p.traces_tags),
    labels: p.labels || null, scans: 0,
    last_modified: p.last_modified_t ? new Date(p.last_modified_t * 1000).toISOString().slice(0, 10) : null,
  };
}

// One product by barcode: our database first, then a live Open Food Facts lookup.
// Returns { product, live } or null. product.nutrients is an object.
export async function getProduct(env, code) {
  const codes = barcodeVariants(code);
  if (!codes.length) return null;
  const product = await pdb(env).prepare("SELECT * FROM products WHERE code IN (SELECT value FROM json_each(?1)) LIMIT 1")
    .bind(JSON.stringify(codes)).first();
  if (product) {
    product.nutrients = JSON.parse(product.nutrients);
    delete product.search_text;
    return { product, live: false };
  }
  const live = await lookupLive(codes[0]);
  return live ? { product: live, live: true } : null;
}
