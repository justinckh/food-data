"""Database-wide food categories: one list for all sources (foods.category).

Each source has its own groups (172 group/subgroup pairs in total). This step maps them
to one shared list, so the site can browse the whole database by category.

Order of the rules for one food:
  1. SUBGROUP[source][(group, subgroup)]  - for mixed groups (e.g. HK cereals: rice AND cakes)
  2. GROUP[source][group]                 - the normal case
  3. name rules (NAME_RULES), which move a food out of a mixed category by its name,
     e.g. chicken in TFDA/MEXT "Meat" -> poultry; sake in MEXT "Beverages" -> alcohol.
Foods without a mapping go to 'other'.
"""
import re

from . import subcategories

# id, Chinese (HK), English - in display order
CATEGORIES = [
    ("cereals", "穀物米麵", "Cereals, rice & noodles"),
    ("bakery", "麵包糕點及餅乾", "Bread, cakes & biscuits"),
    ("starchy", "薯類及澱粉", "Potatoes, tubers & starches"),
    ("legumes", "豆類及豆製品", "Legumes & soy products"),
    ("vegetables", "蔬菜", "Vegetables"),
    ("fungi_algae", "菇菌及海藻", "Mushrooms & seaweed"),
    ("fruits", "水果", "Fruits"),
    ("nuts", "堅果及種子", "Nuts & seeds"),
    ("meat", "肉類", "Meat"),
    ("poultry", "家禽", "Poultry"),
    ("seafood", "魚類及海產", "Fish & seafood"),
    ("eggs", "蛋類", "Eggs"),
    ("dairy", "奶類及奶製品", "Dairy"),
    ("fats", "油脂", "Fats & oils"),
    ("sweets", "糖果甜品", "Sugars, sweets & desserts"),
    ("snacks", "零食", "Snacks"),
    ("drinks", "飲品", "Drinks"),
    ("alcohol", "酒類", "Alcoholic drinks"),
    ("condiments", "調味料及醬料", "Condiments, sauces & spices"),
    ("soups", "湯類", "Soups"),
    ("dishes", "菜式及即食食品", "Dishes & ready-to-eat foods"),
    ("baby", "嬰兒食品", "Baby foods"),
    ("other", "其他", "Other"),
]
IDS = {c[0] for c in CATEGORIES}

GROUP = {
    "cfs": {
        "Alcoholic beverages": "alcohol", "Aquatic animals other than fish": "seafood", "Baby foods": "baby",
        "Cereals and cereal products": "cereals", "Condiments and sauces": "condiments",
        "Eggs and egg products": "eggs", "Fats and oils": "fats", "Fish and fish products": "seafood",
        "Frozen confections": "sweets", "Fruits and fruit products": "fruits", "Games and game products": "meat",
        "Herbs and spices": "condiments", "Legumes and legume products": "legumes",
        "Meat and meat products": "meat", "Milk and milk products": "dairy", "Non-alcoholic beverages": "drinks",
        "Nuts, seeds and their products": "nuts", "Poultry and poultry products": "poultry",
        "Ready-to-eat foods": "dishes", "Snacks": "snacks", "Soups": "soups", "Sugars and sweets": "sweets",
        "Vegetables and vegetable products": "vegetables",
    },
    "tfda": {
        "Algae and seaweeds": "fungi_algae", "Beverages": "drinks", "Cakes, pastries and snacks": "bakery",
        "Cereals and grains": "cereals", "Dairy": "dairy", "Eggs": "eggs", "Fats and oils": "fats",
        "Fish and shellfish": "seafood", "Fruits": "fruits", "Legumes": "legumes", "Meat": "meat",
        "Mushrooms": "fungi_algae", "Nuts and seeds": "nuts", "Processed and prepared foods, other": "dishes",
        "Seasonings and spices": "condiments", "Starchy foods": "starchy", "Sugars": "sweets",
        "Vegetables": "vegetables",
    },
    "mext": {
        "Algae": "fungi_algae", "Beverages": "drinks", "Cereals": "cereals", "Confectioneries": "bakery",
        "Eggs": "eggs", "Fats and oils": "fats", "Fish, mollusks and crustaceans": "seafood", "Fruits": "fruits",
        "Meat": "meat", "Milk and milk products": "dairy", "Mushrooms": "fungi_algae", "Nuts and seeds": "nuts",
        "Potatoes and starches": "starchy", "Prepared foods": "dishes", "Pulses": "legumes",
        "Seasonings and spices": "condiments", "Sugars and sweeteners": "sweets", "Vegetables": "vegetables",
    },
    "usda": {   # usda_fnd, usda_sr and cnf share these group names (with small spelling differences)
        "American Indian/Alaska Native Foods": "other", "Baby Foods": "baby", "Babyfoods": "baby",
        "Baked Products": "bakery", "Beef Products": "meat", "Beverages": "drinks",
        "Breakfast Cereals": "cereals", "Breakfast cereals": "cereals", "Cereal Grains and Pasta": "cereals",
        "Cereals, Grains and Pasta": "cereals", "Dairy and Egg Products": "dairy", "Fast Foods": "dishes",
        "Fats and Oils": "fats", "Finfish and Shellfish Products": "seafood", "Fruits and Fruit Juices": "fruits",
        "Fruits and fruit juices": "fruits", "Lamb, Veal, and Game Products": "meat", "Lamb, Veal and Game": "meat",
        "Legumes and Legume Products": "legumes", "Meals, Entrees, and Side Dishes": "dishes",
        "Mixed Dishes": "dishes", "Nut and Seed Products": "nuts", "Nuts and Seeds": "nuts",
        "Pork Products": "meat", "Poultry Products": "poultry", "Restaurant Foods": "dishes",
        "Sausages and Luncheon Meats": "meat", "Sausages and Luncheon meats": "meat", "Snacks": "snacks",
        "Soups, Sauces, and Gravies": "soups", "Soups, Sauces and Gravies": "soups",
        "Spices and Herbs": "condiments", "Sweets": "sweets", "Vegetables and Vegetable Products": "vegetables",
    },
    "afcd": {
        "Alcoholic beverages": "alcohol", "Cereal based products and dishes": "bakery",
        "Cereals and cereal products": "cereals", "Confectionery and cereal/nut/fruit/seed bars": "sweets",
        "Dairy & meat substitutes": "legumes", "Egg products and dishes": "eggs", "Fats and oils": "fats",
        "Fish and seafood products and dishes": "seafood", "Fruit products and dishes": "fruits",
        "Infant formulae and foods": "baby", "Legume and pulse products and dishes": "legumes",
        "Meat, poultry and game products and dishes": "meat", "Milk products and dishes": "dairy",
        "Miscellaneous": "other", "Non-alcoholic beverages": "drinks", "Reptiles, amphibia and insects": "other",
        "Savoury sauces and condiments": "condiments", "Seed and nut products and dishes": "nuts",
        "Snack foods": "snacks", "Soup": "soups", "Special dietary foods": "other",
        "Sugar products and dishes": "sweets", "Vegetable products and dishes": "vegetables",
    },
    "cofid": {
        "Alcoholic beverages": "alcohol", "Beverages": "drinks", "Cereals and cereal products": "cereals",
        "Eggs": "eggs", "Fats and oils": "fats", "Fish and fish products": "seafood", "Fruit": "fruits",
        "Herbs and spices": "condiments", "Meat and meat products": "meat", "Milk and milk products": "dairy",
        "Nuts and seeds": "nuts", "Soups, sauces and miscellaneous foods": "condiments",
        "Sugars, preserves and snacks": "sweets", "Vegetables": "vegetables",
    },
}
GROUP["usda_fnd"] = GROUP["usda_sr"] = GROUP["cnf"] = GROUP["usda"]


def _sub(group, mapping):
    return {(group, sg): cat for sg, cat in mapping.items()}


SUBGROUP = {
    "cfs": {
        **_sub("Cereals and cereal products", {
            "Biscuits and crackers": "bakery", "Breads and rolls": "bakery", "Cakes, cookies, pies and pastries": "bakery",
            "Muffins": "bakery", "Pancakes and waffles": "bakery"}),
        **_sub("Vegetables and vegetable products", {"Mushrooms and seaweeds": "fungi_algae"}),
    },
    "afcd": {
        **_sub("Cereal based products and dishes", {"Mixed dishes where cereal is the major ingredient": "dishes"}),
        **_sub("Cereals and cereal products", {
            "English-style muffins, flat breads, and savoury and sweet breads": "bakery",
            "Regular breads, and bread rolls (plain/unfilled/untopped varieties)": "bakery"}),
        **_sub("Dairy & meat substitutes", {"Cheese substitute": "dairy", "Dairy milk substitutes, unflavoured": "drinks",
                                            "Soy-based yoghurts": "dairy"}),
        **_sub("Meat, poultry and game products and dishes", {
            "Poultry and feathered game": "poultry",
            "Mixed dishes where poultry or feathered game is the major component": "dishes",
            "Mixed dishes where beef, sheep, pork or mammalian game is the major component": "dishes"}),
        **_sub("Milk products and dishes", {"Frozen milk products": "sweets"}),
        **_sub("Miscellaneous", {"Herbs, spices, seasonings and stock cubes": "condiments"}),
        **_sub("Vegetable products and dishes", {"Potatoes": "starchy"}),
    },
    "cofid": {
        **_sub("Cereals and cereal products", {
            "Biscuits": "bakery", "Breads": "bakery", "Buns and pastries": "bakery", "Cakes": "bakery",
            "Pastry": "bakery", "Rolls": "bakery", "Puddings": "sweets", "Pizzas": "dishes", "Sandwiches": "dishes",
            "Savouries": "dishes", "Infant cereal foods": "baby"}),
        **_sub("Meat and meat products", {
            "Chicken": "poultry", "Duck": "poultry", "Goose": "poultry", "Grouse": "poultry", "Partridge": "poultry",
            "Pheasant": "poultry", "Pigeon": "poultry", "Turkey": "poultry", "Meat dishes": "dishes"}),
        **_sub("Milk and milk products", {"Ice creams": "sweets", "Puddings and chilled desserts": "sweets",
                                          "Savoury dishes and sauces": "dishes"}),
        **_sub("Soups, sauces and miscellaneous foods", {
            "Canned soups": "soups", "Homemade soups": "soups", "Packet soups": "soups", "Soups": "soups",
            "Miscellaneous foods": "other"}),
        **_sub("Sugars, preserves and snacks", {"Non-potato snacks": "snacks", "Potato-based snacks": "snacks",
                                               "Savoury snacks": "snacks"}),
        **_sub("Vegetables", {
            "Chipped old potatoes": "starchy", "Early potatoes": "starchy", "Main crop potatoes": "starchy",
            "Potato products": "starchy", "Potatoes": "starchy", "Beans and lentils": "legumes"}),
    },
}

# (from category, pattern on English name, pattern on Chinese/local name, to category)
NAME_RULES = [
    ("meat", r"\b(chicken|duck|goose|turkey|quail|pigeon|squab|poultry|hen|broiler)", r"雞|鴨|鵝|鴿|鵪鶉|にわとり|あひる|がちょう|うずら|しちめんちょう", "poultry"),
    ("drinks", r"\b(wine|(?<!root )(?<!ginger )beer|sake|whisk(e)?y|spirit|liqueur|shochu|brandy|vodka|gin|rum|alcoholic|(?<!soft )cider|mirin)\b",
     r"酒|ビール|ワイン|焼酎|ウイスキー|ブランデー|リキュール|みりん", "alcohol"),
    ("dairy", r"^eggs?\b|\begg (white|yolk|substitute)", r"^雞蛋|^蛋", "eggs"),
    ("soups", r"\b(sauce|gravy|gravies|dip|dressing|salsa)\b", r"醬|汁", "condiments"),
    ("vegetables", r"\b(potato|potatoes|cassava|yam|taro)\b", r"薯|芋", "starchy"),
    ("vegetables", r"\b(mushroom|mushrooms|seaweed|kelp|nori|laver|agar|wakame|spirulina)\b", r"菇|菌|蕈|海帶|紫菜|海藻|木耳", "fungi_algae"),
    # MEXT "Confectioneries" mixes cakes and candy
    ("bakery", r"\b(candy|candies|caramel|gum|chocolate|jelly|jellies|marshmallow|toffee|drops?)\b",
     r"キャンデー|キャラメル|ガム|チョコレート|ゼリー|ドロップ|糖果|巧克力", "sweets"),
    # USDA "American Indian/Alaska Native Foods" and other unmapped foods, sorted by name
    ("other", r"\b(fish|salmon|trout|whitefish|smelt|mollusks?|cockle|clam|seal|whale|walrus|octopus|crab|shrimp)\b", r"魚|蝦|蟹|貝", "seafood"),
    ("other", r"\b(elk|moose|caribou|deer|venison|game meat|beef|bear|buffalo|bison|rabbit|beaver|muskrat|squirrel)\b", r"肉", "meat"),
    ("other", r"\b(duck|goose|grouse|ptarmigan)\b", r"鴨|鵝", "poultry"),
    ("other", r"\b(stew|soup|chowder|broth)\b", r"湯|羹", "soups"),
    ("other", r"(berr(y|ies)\b|\bchokecherries\b|\bfruit|\bplums?\b|\brose hips\b|\bprickly pears?\b)", r"果", "fruits"),
    ("other", r"\b(squash|corn|beans|greens|leaves|shoots|roots|cattail|fireweed|seaweed)\b", r"菜", "vegetables"),
    ("other", r"\b(bread|frybread|tortilla)\b", r"包|餅", "bakery"),
    ("other", r"\b(oil|fat|grease|lard|blubber)\b", r"油", "fats"),
]
NAME_RULES = [(f, re.compile(en, re.I), re.compile(zh), t) for f, en, zh, t in NAME_RULES]


def category_for(src, group, subgroup, name_en, name_zh):
    cat = SUBGROUP.get(src, {}).get((group, subgroup)) or GROUP.get(src, {}).get(group) or "other"
    for frm, en_pat, zh_pat, to in NAME_RULES:
        if cat == frm and ((name_en and en_pat.search(name_en)) or (name_zh and zh_pat.search(name_zh))):
            cat = to
            break
    return cat


def run(db):
    rows = db.execute("SELECT id, source_id, coalesce(group_en, group_zh), subgroup_en, name_en, "
                      "coalesce(name_zh, name_local) FROM foods").fetchall()
    updates = [(category_for(src, g, sg, en, zh), fid) for fid, src, g, sg, en, zh in rows]
    db.execute("DELETE FROM categories")
    db.executemany("INSERT INTO categories (id, name_zh, name_en, sort_order) VALUES (?, ?, ?, ?)",
                   [(*c, i) for i, c in enumerate(CATEGORIES)])
    db.executemany("UPDATE foods SET category = ? WHERE id = ?", updates)
    # subcategories by name (English, Chinese incl. shown/translated name, Japanese)
    cat = {fid: c for c, fid in updates}
    subs = [(subcategories.sub_for(cat[fid], en, (zh, dzh, local)), fid) for fid, en, zh, dzh, local in
            db.execute("SELECT id, name_en, name_zh, display_zh, name_local FROM foods")]
    db.execute("DELETE FROM subcategories")
    db.executemany("INSERT INTO subcategories (id, category, name_zh, name_en, sort_order) VALUES (?, ?, ?, ?, ?)",
                   subcategories.rows())
    db.executemany("UPDATE foods SET subcategory = ? WHERE id = ?", subs)
    other = sum(1 for c, _ in updates if c == "other")
    print(f"  Categories            {len(updates)} foods in {len({c for c, _ in updates})} categories ({other} other)")
