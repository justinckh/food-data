"""Importer: Canadian Nutrient File (CNF) 2015, Health Canada.

Input: data/raw/cnf/cnf-fcen-csv.zip (the CSV download, read in place).
Tables used: FOOD NAME, FOOD GROUP, NUTRIENT NAME, NUTRIENT AMOUNT,
CONVERSION FACTOR, MEASURE NAME. Text tables are Windows-1252; NUTRIENT AMOUNT is ASCII.

Nutrients are matched by NutrientCode (the same numbers as USDA SR Legacy) and the
unit is checked. NutrientID differs from NutrientCode for some nutrients, so amounts
are joined through NutrientID. Values are plain numbers (no markers).

Servings: CNF conversion factors are multiples of 100 g, so grams = factor x 100.
French names go to name_local. FOOD SOURCE descriptions go to origin_source
(62% of foods are USDA data with no changes).

Not imported yet: individual sugars, starch, amino acids, individual fatty acids,
phytosterols, choline, betaine, other tocopherols, vitamin D in IU, folate forms.

Licence: Open Government Licence - Canada.
"""
import csv
import io
import zipfile
from datetime import date

from ..common import clean, search_text

RAW = "data/raw/cnf"
FILE = "cnf-fcen-csv.zip"

# NutrientCode -> (our id, CNF unit, method)
NUTRIENT_MAP = {
    "208": ("energy_kcal", "kCal", None), "268": ("energy_kj", "kJ", None),
    "203": ("protein", "g", None), "204": ("fat", "g", None),
    "205": ("carbohydrate", "g", "difference"), "291": ("fibre", "g", None),
    "269": ("sugars", "g", None), "255": ("water", "g", None), "207": ("ash", "g", None),
    "221": ("alcohol", "g", None), "262": ("caffeine", "mg", None),
    "601": ("cholesterol", "mg", None), "606": ("fat_sat", "g", None),
    "645": ("fat_mono", "g", None), "646": ("fat_poly", "g", None), "605": ("fat_trans", "g", None),
    "301": ("calcium", "mg", None), "303": ("iron", "mg", None), "304": ("magnesium", "mg", None),
    "305": ("phosphorus", "mg", None), "306": ("potassium", "mg", None), "307": ("sodium", "mg", None),
    "309": ("zinc", "mg", None), "312": ("copper", "mg", None), "315": ("manganese", "mg", None),
    "317": ("selenium", "µg", None),
    "319": ("retinol", "µg", None), "320": ("vitamin_a_rae", "µg", None),
    "321": ("beta_carotene", "µg", None), "322": ("alpha_carotene", "µg", None),
    "334": ("beta_cryptoxanthin", "µg", None), "323": ("alpha_tocopherol", "mg", None),
    "328": ("vitamin_d", "µg", None), "401": ("vitamin_c", "mg", None),
    "404": ("vitamin_b1", "mg", None), "405": ("vitamin_b2", "mg", None), "406": ("niacin", "mg", None),
    "409": ("niacin_eq", "NE", None),          # CNF unit "NE" = mg niacin equivalents
    "410": ("pantothenic_acid", "mg", None), "415": ("vitamin_b6", "mg", None),
    "416": ("biotin", "µg", None), "417": ("folate", "µg", None), "418": ("vitamin_b12", "µg", None),
    "430": ("vitamin_k1", "µg", None),         # USDA/CNF 430 = phylloquinone
}

SOURCE = {
    "id": "cnf",
    "name": "Canadian Nutrient File (CNF) 2015",
    "publisher": "Health Canada",
    "country": "CA",
    "licence": "Open Government Licence - Canada",
    "attribution": "Contains information licensed under the Open Government Licence - Canada. "
                   "Health Canada, Canadian Nutrient File, 2015.",
    "url": "https://www.canada.ca/en/health-canada/services/food-nutrition/healthy-eating/nutrient-data.html",
    "version": "2015",
}


def table(zf, name):
    raw = zf.read(name)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
    return list(csv.DictReader(io.StringIO(text)))


def load(path):
    zf = zipfile.ZipFile(path)
    groups = {g["FoodGroupID"]: clean(g["FoodGroupName"]) for g in table(zf, "FOOD GROUP.csv")}
    # Where each food's data comes from, e.g. "FOODS BASED ON DATA FROM USDA: NO CHANGES"
    # (about 62% of foods). Kept so USDA copies can be linked later.
    origins = {o["FoodSourceID"].strip(): clean(o["FoodSourceDescription"]) for o in table(zf, "FOOD SOURCE.csv")}

    by_id = {}
    for n in table(zf, "NUTRIENT NAME.csv"):
        hit = NUTRIENT_MAP.get(n["NutrientCode"].strip())
        if hit:
            if n["NutrientUnit"].strip() != hit[1]:
                raise SystemExit(f"cnf: nutrient {n['NutrientCode']} unit is {n['NutrientUnit']!r}, expected {hit[1]!r}")
            by_id[n["NutrientID"].strip()] = (hit[0], hit[2])
    if len(by_id) != len(NUTRIENT_MAP):
        raise SystemExit(f"cnf: found {len(by_id)} of {len(NUTRIENT_MAP)} mapped nutrients")

    values = {}
    for a in table(zf, "NUTRIENT AMOUNT.csv"):
        hit = by_id.get(a["NutrientID"].strip())
        v = a["NutrientValue"].strip()
        if hit and v:
            values.setdefault(a["FoodID"].strip(), []).append((hit[0], float(v), None, hit[1]))

    measures = {m["MeasureID"].strip(): clean(m["MeasureDescription"]) for m in table(zf, "MEASURE NAME.csv")}
    servings = {}
    for c in table(zf, "CONVERSION FACTOR.csv"):
        label = measures.get(c["MeasureID"].strip())
        factor = c["ConversionFactorValue"].strip()
        if label and factor and float(factor) > 0:
            servings.setdefault(c["FoodID"].strip(), []).append(
                (label, None, round(float(factor) * 100, 3), "g"))

    for f in table(zf, "FOOD NAME.csv"):
        fid = f["FoodID"].strip()
        food = {
            "id": f"cnf:{fid}",
            "source_id": "cnf",
            "source_code": fid,
            "name_en": clean(f["FoodDescription"]),
            "name_local": clean(f["FoodDescriptionF"]) or None,     # French
            "group_en": groups.get(f["FoodGroupID"].strip()),
            "origin_source": origins.get(f["FoodSourceID"].strip()),
        }
        food["search_text"] = search_text(food)
        yield food, values.get(fid, []), servings.get(fid, [])


def datasets(root):
    path = root / RAW / FILE
    if not path.exists():
        print(f"  cnf        skipped: no {FILE} in {RAW}/ (download the CSV zip from Health Canada)")
        return
    src = dict(SOURCE, retrieved_at=date.fromtimestamp(path.stat().st_mtime).isoformat())
    yield src, load(path)
