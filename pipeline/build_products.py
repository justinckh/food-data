"""Build the packaged-food products database from the Open Food Facts CSV export.

Run from the project root:   python3 -m pipeline.build_products   -> data/export/products.db
                              python3 -m pipeline.build_products --sql   (also writes products.sql)

Input:  data/raw/off/en.openfoodfacts.org.products.csv.gz  (download: npm run download:off)
        The file is read compressed, row by row. It is not extracted.
Scope:  products whose "sold in" countries (countries_tags) include an Asian market (MARKETS).
        Products sold elsewhere only are not stored; the API looks them up live on Open Food Facts.
Values: as printed on the package (per 100 g / 100 ml). The site does NOT recalculate energy for
        products (unlike foods, PROJECT.md 3.10.2): a label value is what the buyer sees.
Licence: Open Food Facts database = ODbL 1.0, contents = DbCL 1.0, images = CC BY-SA.

Served tables: product_categories, product_markets, products (+ products_fts trigram index).
"""
import csv
import gzip
import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "off" / "en.openfoodfacts.org.products.csv.gz"
OUT = ROOT / "data" / "export" / "products.db"
SQL_OUT = ROOT / "data" / "export" / "products.sql"

csv.field_size_limit(sys.maxsize)

# countries_tags value -> (code, Chinese name). Order = order on the site.
MARKETS = {
    "en:hong-kong": ("HK", "香港"), "en:macau": ("MO", "澳門"), "en:taiwan": ("TW", "台灣"),
    "en:china": ("CN", "中國內地"), "en:japan": ("JP", "日本"), "en:south-korea": ("KR", "韓國"),
    "en:singapore": ("SG", "新加坡"), "en:malaysia": ("MY", "馬來西亞"), "en:thailand": ("TH", "泰國"),
    "en:philippines": ("PH", "菲律賓"), "en:indonesia": ("ID", "印尼"), "en:vietnam": ("VN", "越南"),
    "en:india": ("IN", "印度"),
}

# Product categories for the site. A product goes to the FIRST category with a matching
# Open Food Facts category tag (categories_tags), so specific rules come before general ones.
CATEGORIES = [
    ("baby", "嬰幼兒食品", "Baby food", ["en:baby-foods", "en:baby-milks", "en:infant-formulas"]),
    ("supplements", "營養補充品", "Supplements", ["en:dietary-supplements", "en:food-supplements"]),
    ("alcohol", "酒精飲品", "Alcoholic drinks", ["en:alcoholic-beverages", "en:beers", "en:wines", "en:sakes"]),
    ("ice_cream", "雪糕及甜品", "Ice cream & desserts", ["en:ice-creams-and-sorbets", "en:ice-creams", "en:frozen-desserts", "en:desserts", "en:puddings", "en:jellies"]),
    ("dairy", "奶類及乳製品", "Dairy", ["en:dairies", "en:milks", "en:yogurts", "en:cheeses", "en:fermented-milk-products"]),
    ("drinks", "飲品", "Drinks", ["en:beverages", "en:waters", "en:teas", "en:coffees", "en:juices-and-nectars", "en:sodas", "en:plant-based-milks"]),
    ("sweets", "糖果及朱古力", "Sweets & chocolate", ["en:chocolates", "en:candies", "en:confectioneries", "en:chewing-gum", "en:cocoa-and-its-products"]),
    ("biscuits", "餅乾及糕點", "Biscuits & cakes", ["en:biscuits-and-cakes", "en:biscuits", "en:cakes", "en:pastries", "en:viennoiseries", "en:wafers"]),
    ("snacks", "零食", "Snacks", ["en:salty-snacks", "en:snacks", "en:crisps", "en:chips-and-fries", "en:crackers", "en:popcorn", "en:nuts", "en:dried-fruits", "en:seaweed-snacks"]),
    ("noodles", "麵、米及意粉", "Noodles, rice & pasta", ["en:instant-noodles", "en:noodles", "en:pastas", "en:rices", "en:cereal-grains"]),
    ("breakfast", "早餐穀物及麵包", "Cereals & bread", ["en:breakfast-cereals", "en:breads", "en:cereals-and-their-products"]),
    ("spreads", "果醬及抹醬", "Spreads", ["en:spreads", "en:jams", "en:honeys", "en:sweet-spreads", "en:nut-butters"]),
    ("sauces", "醬料及調味", "Sauces & seasonings", ["en:sauces", "en:condiments", "en:seasonings", "en:spices", "en:vinegars", "en:fats", "en:vegetable-oils", "en:salts", "en:sugars"]),
    ("meals", "即食及罐頭", "Ready meals & canned", ["en:meals", "en:prepared-meals", "en:soups", "en:canned-foods", "en:frozen-foods", "en:dumplings"]),
    ("meat_fish", "肉類及海產", "Meat & seafood", ["en:meats", "en:meat-products", "en:seafood", "en:fishes", "en:fish-and-seafood"]),
    ("plant", "蔬果、豆類及豆腐", "Fruit, veg & soy", ["en:fruits-and-vegetables-based-foods", "en:fruits", "en:vegetables", "en:legumes", "en:tofu", "en:plant-based-foods"]),
    ("other", "其他／未分類", "Other / not classified", []),
]
# 77 % of the Asian products have no Open Food Facts category. For those, the product name decides
# (English, Chinese, Japanese words). First matching rule wins: product types (chips, wafer, tuna)
# come before flavour words (cheese, milk, oil), so "cheese corn chips" is a snack.
NAME_RULES = [(c, re.compile(r, re.I)) for c, r in [
    ("baby", r"infant formula|baby food|嬰兒|婴儿|幼兒|ベビー|離乳食|育児用"),
    ("supplements", r"supplement|capsule|tablet|vitamin [a-z]?\d*\s*(mg|iu)|\d+\s*mg\b|保健|膠囊|サプリ|錠"),
    ("alcohol", r"\b(beer|lager|wine|whisk(e)?y|vodka|gin|rum|sake|soju|cider|liqueur|chuhai|highball)\b|啤酒|紅酒|白酒|清酒|燒酒|ビール|ワイン|日本酒|焼酎|チューハイ|ハイボール|梅酒|発泡酒"),
    ("sweets", r"chocolate|candy|candies|gummy|gummies|lollipop|toffee|caramel|marshmallow|chewing gum|mints?\b|朱古力|巧克力|糖果|軟糖|香口膠|チョコ|キャンディ|グミ|ガム|飴|キャラメル"),
    ("biscuits", r"biscuit|cookie|wafer|cake|brownie|muffin|croissant|pastry|pie\b|tart|donut|doughnut|swiss roll|餅乾|饼干|曲奇|蛋糕|蛋捲|威化|酥|餅|ビスケット|クッキー|ウエハース|ケーキ|パイ|ドーナツ|カステラ|せんべい|煎餅|まんじゅう|饅頭|羊羹"),
    ("snacks", r"\bchips?\b|crisps|cracker|popcorn|pretzel|nuts?\b|almond|cashew|peanut|pistachio|trail mix|namkeen|bhujia|farsan|chevda|mixture|makhana|seaweed|jerky|薯片|薯條|脆|堅果|花生|杏仁|紫菜|海苔|零食|スナック|ポテト|あられ|おかき|ナッツ|ピーナッツ"),
    ("ice_cream", r"ice ?cream|gelato|sorbet|pudding|jelly|mochi|雪糕|冰淇淋|布丁|果凍|啫喱|アイス|プリン|ゼリー|大福"),
    ("noodles", r"noodle|ramen|udon|soba|pasta|spaghetti|macaroni|vermicelli|\brice\b|basmati|麵|面$|拉麵|米粉|粉絲|意粉|通心粉|白米|米$|ラーメン|うどん|そば|焼きそば|パスタ|スパゲッティ|米$|ごはん|ご飯"),
    ("meat_fish", r"\b(chicken|beef|pork|ham|bacon|sausage|salami|tuna|salmon|sardine|fish|prawn|shrimp|crab|squid)\b|雞|鸡|牛肉|豬|猪|火腿|香腸|魚|鱼|蝦|虾|蟹|肉|ハム|ソーセージ|ベーコン|ツナ|鮭|さけ|さば|魚|えび|かに|チキン|ポーク|ビーフ"),
    ("meals", r"instant|ready meal|soup|curry|biryani|dumpling|bento|sandwich|onigiri|pizza|burger|frozen|canned|即食|杯麵|湯|餃子|水餃|便當|罐頭|冷凍|弁当|おにぎり|サンド|カレー|スープ|餃子|冷凍|惣菜|丼"),
    ("dairy", r"\b(milk|yogh?urt|cheese|butter|kefir|ghee|paneer|dahi|curd)\b|牛奶|鮮奶|鲜奶|乳酪|優格|酸奶|芝士|起司|牛乳|ヨーグルト|チーズ|バター|乳飲料"),
    ("drinks", r"\b(juice|water|soda|cola|tea|coffee|latte|drink|beverage|lemonade|smoothie|kombucha|sparkling|energy drink|soy ?milk|oat ?milk)\b|飲料|饮料|汁|茶|咖啡|可樂|汽水|豆奶|豆漿|水$|ジュース|飲料|ドリンク|お茶|緑茶|コーヒー|サイダー|ウォーター|豆乳|ラテ"),
    ("breakfast", r"cereal|granola|muesli|oats|oatmeal|cornflakes|bread|toast|bagel|\bbun\b|roti|chapati|naan|麥片|麦片|燕麥|麵包|面包|吐司|シリアル|グラノーラ|オートミール|パン|食パン"),
    ("spreads", r"\bjam\b|marmalade|honey|peanut butter|nutella|spread|果醬|蜂蜜|花生醬|ジャム|はちみつ|蜂蜜"),
    ("sauces", r"sauce|ketchup|mayonnaise|mayo|dressing|vinegar|soy sauce|seasoning|spice|masala|curry paste|\boil\b|\bsalt\b|\bsugar\b|pickle|chutney|醬|酱|醋|油$|鹽|糖$|調味|咖喱|ソース|しょうゆ|醤油|酢|味噌|みそ|ドレッシング|マヨネーズ|だし|調味|スパイス|カレールー|塩"),
    ("plant", r"\b(tofu|beans?|lentils?|dal|chickpeas?|fruit|apple|banana|mango|vegetables?|kimchi|mushroom|dates)\b|豆腐|豆|果|菜|菇|蔬|納豆|なっとう|豆腐|野菜|果物|フルーツ|キムチ|きのこ"),
]]
# Not food (Open Beauty / Products Facts entries tagged as sold in Asia): not stored.
NON_FOOD_TAGS = ("en:cosmetic", "en:open-beauty-facts", "en:open-products-facts", "en:toothpaste", "en:soaps", "en:sunscreen",
                 "en:to-be-deleted", "en:shampoo", "en:deodorant", "en:non-food", "en:pet-food", "en:cat-food", "en:dog-food")
# Russian-language entries (Cyrillic name, brand or ingredients) are not stored (user decision 2026-11-13).
CYRILLIC = re.compile(r"[\u0400-\u04FF]")
NON_FOOD_NAME = re.compile(r"toothpaste|shampoo|sunscreen|\bsoap\b|deodorant|lotion|vaporub|detergent|牙膏|洗髮|沐浴|歯磨き|シャンプー", re.I)

CAT_OF_TAG = {}
for cid, _, _, tags in CATEGORIES:
    for t in tags:
        CAT_OF_TAG.setdefault(t, cid)
CAT_ORDER = {c[0]: i for i, c in enumerate(CATEGORIES)}

# OFF column -> (our nutrient id, factor). OFF stores mass values in grams per 100 g.
NUTRIENT_MAP = {
    "energy-kcal_100g": ("energy_kcal", 1), "energy-kj_100g": ("energy_kj", 1),
    "proteins_100g": ("protein", 1), "carbohydrates_100g": ("carbohydrate", 1), "fat_100g": ("fat", 1),
    "saturated-fat_100g": ("fat_sat", 1), "trans-fat_100g": ("fat_trans", 1),
    "monounsaturated-fat_100g": ("fat_mono", 1), "polyunsaturated-fat_100g": ("fat_poly", 1),
    "cholesterol_100g": ("cholesterol", 1e3), "fiber_100g": ("fibre", 1), "sugars_100g": ("sugars", 1),
    "sodium_100g": ("sodium", 1e3), "salt_100g": ("salt_eq", 1),
    "potassium_100g": ("potassium", 1e3), "calcium_100g": ("calcium", 1e3), "magnesium_100g": ("magnesium", 1e3),
    "phosphorus_100g": ("phosphorus", 1e3), "iron_100g": ("iron", 1e3), "zinc_100g": ("zinc", 1e3),
    "copper_100g": ("copper", 1e3), "manganese_100g": ("manganese", 1e3), "vitamin-c_100g": ("vitamin_c", 1e3),
    "vitamin-a_100g": ("vitamin_a_re", 1e6), "beta-carotene_100g": ("beta_carotene", 1e6),
    "vitamin-d_100g": ("vitamin_d", 1e6), "vitamin-e_100g": ("vitamin_e_ate", 1e3), "vitamin-k_100g": ("vitamin_k", 1e6),
    "vitamin-b1_100g": ("vitamin_b1", 1e3), "vitamin-b2_100g": ("vitamin_b2", 1e3), "vitamin-pp_100g": ("niacin", 1e3),
    "vitamin-b6_100g": ("vitamin_b6", 1e3), "vitamin-b9_100g": ("folate", 1e6), "vitamin-b12_100g": ("vitamin_b12", 1e6),
    "biotin_100g": ("biotin", 1e6), "pantothenic-acid_100g": ("pantothenic_acid", 1e3),
    "iodine_100g": ("iodine", 1e6), "selenium_100g": ("selenium", 1e6), "chromium_100g": ("chromium", 1e6),
    "molybdenum_100g": ("molybdenum", 1e6), "caffeine_100g": ("caffeine", 1e3), "water_100g": ("water", 1),
}
GRAM_IDS = {"protein", "carbohydrate", "fat", "fat_sat", "fat_trans", "fat_mono", "fat_poly", "fibre", "sugars", "salt_eq", "water"}
KEY = ["energy_kcal", "protein", "fat", "carbohydrate", "sugars", "fibre", "sodium"]

SCHEMA = f"""
CREATE TABLE product_categories (id TEXT PRIMARY KEY, name_zh TEXT NOT NULL, name_en TEXT NOT NULL,
    sort_order INTEGER NOT NULL, n INTEGER NOT NULL);
CREATE TABLE product_markets (id TEXT PRIMARY KEY, name_zh TEXT NOT NULL, sort_order INTEGER NOT NULL, n INTEGER NOT NULL);
CREATE TABLE products (
    code TEXT PRIMARY KEY,            -- barcode (EAN-13, UPC-A, EAN-8 ...)
    name TEXT NOT NULL, generic_name TEXT, brand TEXT, quantity TEXT,
    category TEXT NOT NULL, off_category TEXT,
    markets TEXT NOT NULL,            -- ',HK,JP,' (leading/trailing comma, for LIKE '%,HK,%')
    countries TEXT,                   -- all "sold in" countries, English
    image TEXT, nutriscore TEXT, nova INTEGER,
    serving_size TEXT, serving_g REAL,
    {", ".join(f"{n} REAL" for n in KEY)},
    nutrients TEXT NOT NULL,          -- JSON {{nutrient id: value}} per 100 g / 100 ml
    has_nutrition INTEGER NOT NULL,
    ingredients TEXT, allergens TEXT, traces TEXT, labels TEXT,
    scans INTEGER NOT NULL,           -- unique scans on Open Food Facts (popularity)
    last_modified TEXT,
    search_text TEXT NOT NULL
) WITHOUT ROWID;
CREATE INDEX products_cat ON products(category, scans DESC);
CREATE VIRTUAL TABLE products_fts USING fts5(code UNINDEXED, search_text, tokenize='trigram', columnsize=0);
"""


def num(s):
    try:
        v = float(s)
    except (TypeError, ValueError):
        return None
    return v if v == v and v >= 0 else None


def clean(s, n=None):
    s = re.sub(r"\s+", " ", (s or "")).strip()
    return (s[:n] if n else s) or None


def nutrients_of(row):
    out = {}
    for col, (nid, factor) in NUTRIENT_MAP.items():
        v = num(row.get(col))
        if v is None:
            continue
        v *= factor
        if nid in GRAM_IDS and v > 100:   # impossible per 100 g: data entry error
            continue
        out[nid] = round(v, 4 if v < 1 else 2)
    if "energy_kcal" not in out and "energy_kj" in out:
        out["energy_kcal"] = round(out["energy_kj"] / 4.184, 1)
    if out.get("energy_kcal", 0) > 950:   # above pure fat: data entry error (often kJ in the kcal field)
        out.pop("energy_kcal")
    return out


def category_of(tags, name):
    best = None
    for t in tags:
        c = CAT_OF_TAG.get(t)
        if c and (best is None or CAT_ORDER[c] < CAT_ORDER[best]):
            best = c
    if best:
        return best
    for c, rx in NAME_RULES:
        if rx.search(name):
            return c
    return "other"


def build(write_sql=False):
    if not RAW.exists():
        sys.exit(f"Missing {RAW}. Run: npm run download:off")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.unlink(missing_ok=True)
    db = sqlite3.connect(OUT)
    db.executescript(SCHEMA)
    seen, cats, mkts, total, skipped_non_food, skipped_cyrillic = set(), Counter(), Counter(), 0, 0, 0
    rows = []
    with gzip.open(RAW, "rt", encoding="utf-8", errors="replace", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t", quoting=csv.QUOTE_NONE):
            total += 1
            ctags = (row.get("countries_tags") or "").split(",")
            markets = [MARKETS[t][0] for t in MARKETS if t in ctags]
            code = (row.get("code") or "").strip()
            name = clean(row.get("product_name"), 200) or clean(row.get("generic_name"), 200)
            if not markets or not code.isdigit() or not name or code in seen:
                continue
            if re.fullmatch(r"[\d\s]+", name):   # the barcode typed as the name
                name = clean(row.get("generic_name"), 200)
                if not name or re.fullmatch(r"[\d\s]+", name):
                    continue
            cat_tags = (row.get("categories_tags") or "").split(",")
            if any(t.startswith(NON_FOOD_TAGS) for t in cat_tags) or NON_FOOD_NAME.search(name):
                skipped_non_food += 1
                continue
            if CYRILLIC.search(" ".join(filter(None, (name, row.get("brands"), row.get("generic_name"), row.get("ingredients_text"))))):
                skipped_cyrillic += 1
                continue
            seen.add(code)
            nut = nutrients_of(row)
            cat = category_of(cat_tags, name)
            brand = clean((row.get("brands") or "").split(",")[0], 80)
            generic = clean(row.get("generic_name"), 200)
            off_cat = clean(row.get("main_category_en"), 80)
            search = " ".join(x for x in [name, generic, brand, clean(row.get("brands")), off_cat,
                                          clean(row.get("categories_en"), 400)] if x)
            ns = clean(row.get("nutriscore_grade"))
            nova = num(row.get("nova_group"))
            rows.append((
                code, name, generic if generic != name else None, brand, clean(row.get("quantity"), 40),
                cat, off_cat, "," + ",".join(markets) + ",", clean(row.get("countries_en"), 300),
                clean(row.get("image_small_url")) or clean(row.get("image_url")),
                ns if ns in ("a", "b", "c", "d", "e") else None, int(nova) if nova in (1, 2, 3, 4) else None,
                clean(row.get("serving_size"), 60), num(row.get("serving_quantity")),
                *[nut.get(k) for k in KEY], json.dumps(nut, separators=(",", ":")),
                1 if any(k in nut for k in ("energy_kcal", "protein", "fat", "carbohydrate")) else 0,
                clean(row.get("ingredients_text"), 3000), clean(row.get("allergens_en"), 300),
                clean(row.get("traces_en"), 300), clean(row.get("labels_en"), 300),
                int(num(row.get("unique_scans_n")) or 0), clean(row.get("last_modified_datetime"), 10),
                search.lower(),
            ))
            cats[cat] += 1
            for m in markets:
                mkts[m] += 1
            if len(rows) >= 5000:
                insert(db, rows)
                rows = []
    insert(db, rows)
    db.executemany("INSERT INTO product_categories VALUES (?,?,?,?,?)",
                   [(c, zh, en, i, cats[c]) for i, (c, zh, en, _) in enumerate(CATEGORIES)])
    db.executemany("INSERT INTO product_markets VALUES (?,?,?,?)",
                   [(code, zh, i, mkts[code]) for i, (code, zh) in enumerate(MARKETS.values())])
    db.execute("INSERT INTO products_fts (code, search_text) SELECT code, search_text FROM products")
    db.commit()
    n = db.execute("SELECT COUNT(*), SUM(has_nutrition), SUM(image IS NOT NULL) FROM products").fetchone()
    print(f"Read {total:,} Open Food Facts products. Stored {n[0]:,} sold in Asian markets "
          f"({n[1]:,} with nutrition facts, {n[2]:,} with a photo).")
    print(f"Skipped {skipped_non_food:,} non-food entries (cosmetics, soap ...) and {skipped_cyrillic:,} Russian-language entries.")
    print("Markets:", ", ".join(f"{c} {mkts[c]:,}" for c, _ in MARKETS.values()))
    print("Categories:", ", ".join(f"{c} {cats[c]:,}" for c, *_ in CATEGORIES))
    if write_sql:
        with open(SQL_OUT, "w", encoding="utf-8") as fh:
            for stmt in ("DROP TABLE IF EXISTS products_fts;", "DROP TABLE IF EXISTS products;",
                         "DROP TABLE IF EXISTS product_categories;", "DROP TABLE IF EXISTS product_markets;"):
                fh.write(stmt + "\n")
            for line in db.iterdump():
                if line.startswith(("BEGIN", "COMMIT")) or "products_fts_" in line or "sqlite_master" in line:
                    continue
                if line.startswith('INSERT INTO "products_fts"'):
                    continue
                fh.write(line + "\n")
            fh.write("INSERT INTO products_fts (code, search_text) SELECT code, search_text FROM products;\n")
        print(f"Wrote {SQL_OUT}")
    db.close()


def insert(db, rows):
    if rows:
        db.executemany(f"INSERT INTO products VALUES ({','.join('?' * len(rows[0]))})", rows)


if __name__ == "__main__":
    build("--sql" in sys.argv)
