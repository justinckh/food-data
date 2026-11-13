"""Importer: Canadian Nutrient File (CNF) 2026, Health Canada.

Input: data/raw/cnf/cnf_fcen_all-files-data_2026.zip (read in place). The Health Canada
site cannot be reached from the build machine; download the zip by hand (PROJECT.md 2.10).
An older 2015 zip (cnf-fcen-csv.zip) in the same folder is ignored.

Tables used (UTF-8): Food_Name, CNF_Food_Group, Food_Source, Nutrient_Name,
Nutrient_Amount, Measure_Name, Measure_Weight_Conversion.

- Nutrients are matched by Nutrient_Code (same numbers as USDA SR Legacy) and the unit
  is checked. Values are plain numbers (no markers).
- Food_Source description -> origin_source (most foods are USDA data);
  USDA_NDB_Code -> origin_code, for exact links to USDA records later.
- Alternate_Description_EN -> alias; Comment_EN -> description; French name -> name_local.
- Servings: Measure_Weight_Conversion rows of type 6 (user-defined, e.g. 250 ml) only.
  Type 3 is refuse (inedible parts) and type 9 is yield (cooked weight from raw);
  neither is a serving. Weights are already in grams.

Not imported yet: individual sugars, starch, amino acids, individual fatty acids,
phytosterols, choline, betaine, other tocopherols, vitamin D in IU, folate forms,
refuse and yield data.

Licence: Open Government Licence - Canada.
"""
import csv
import io
import zipfile
from datetime import date

from ..common import clean, search_text

RAW = "data/raw/cnf"
FILE = "cnf_fcen_all-files-data_2026.zip"

# Nutrient_Code -> (our id, CNF 2026 unit word, method)
NUTRIENT_MAP = {
    "208": ("energy_kcal", "kilocalorie", None), "268": ("energy_kj", "kilojoule", None),
    "203": ("protein", "Gram", None), "204": ("fat", "Gram", None),
    "205": ("carbohydrate", "Gram", "difference"), "291": ("fibre", "Gram", None),
    "269": ("sugars", "Gram", None), "255": ("water", "Gram", None), "207": ("ash", "Gram", None),
    "221": ("alcohol", "Gram", None), "262": ("caffeine", "Milligram", None),
    "601": ("cholesterol", "Milligram", None), "606": ("fat_sat", "Gram", None),
    "645": ("fat_mono", "Gram", None), "646": ("fat_poly", "Gram", None), "605": ("fat_trans", "Gram", None),
    "301": ("calcium", "Milligram", None), "303": ("iron", "Milligram", None),
    "304": ("magnesium", "Milligram", None), "305": ("phosphorus", "Milligram", None),
    "306": ("potassium", "Milligram", None), "307": ("sodium", "Milligram", None),
    "309": ("zinc", "Milligram", None), "312": ("copper", "Milligram", None),
    "315": ("manganese", "Milligram", None), "317": ("selenium", "Microgram", None),
    "319": ("retinol", "Microgram", None), "320": ("vitamin_a_rae", "Microgram", None),
    "321": ("beta_carotene", "Microgram", None), "322": ("alpha_carotene", "Microgram", None),
    "334": ("beta_cryptoxanthin", "Microgram", None), "323": ("alpha_tocopherol", "Milligram", None),
    "328": ("vitamin_d", "Microgram", None), "401": ("vitamin_c", "Milligram", None),
    "404": ("vitamin_b1", "Milligram", None), "405": ("vitamin_b2", "Milligram", None),
    "406": ("niacin", "Milligram", None),
    "409": ("niacin_eq", "Niacin Equivalents", None),   # = mg niacin equivalents
    "410": ("pantothenic_acid", "Milligram", None), "415": ("vitamin_b6", "Milligram", None),
    "416": ("biotin", "Microgram", None), "417": ("folate", "Microgram", None),
    "418": ("vitamin_b12", "Microgram", None),
    "430": ("vitamin_k1", "Microgram", None),           # phylloquinone
}
SERVING_TYPE = "6"   # user-defined measures

SOURCE = {
    "id": "cnf",
    "name": "Canadian Nutrient File (CNF) 2026",
    "publisher": "Health Canada",
    "country": "CA",
    "licence": "Open Government Licence - Canada",
    "attribution": "Contains information licensed under the Open Government Licence - Canada. "
                   "Health Canada, Canadian Nutrient File, 2026.",
    "url": "https://www.canada.ca/en/health-canada/services/food-nutrition/healthy-eating/nutrient-data.html",
    "version": "2026",
}


def table(zf, name):
    return list(csv.DictReader(io.StringIO(zf.read(name).decode("utf-8-sig"))))


def load(path):
    zf = zipfile.ZipFile(path)
    groups = {g["CNF_Food_Group_Code"].strip(): clean(g["CNF_Food_Group_Description_EN"])
              for g in table(zf, "CNF_Food_Group.csv")}
    origins = {o["Food_Source_Code"].strip(): clean(o["Food_Source_Description_EN"])
               for o in table(zf, "Food_Source.csv")}

    found = set()
    for n in table(zf, "Nutrient_Name.csv"):
        code = n["Nutrient_Code"].strip()
        if code in NUTRIENT_MAP:
            if n["Nutrient_Unit"].strip() != NUTRIENT_MAP[code][1]:
                raise SystemExit(f"cnf: nutrient {code} unit is {n['Nutrient_Unit']!r}, "
                                 f"expected {NUTRIENT_MAP[code][1]!r}")
            found.add(code)
    if found != set(NUTRIENT_MAP):
        raise SystemExit(f"cnf: nutrients missing from Nutrient_Name: {sorted(set(NUTRIENT_MAP) - found)}")

    values = {}
    for a in table(zf, "Nutrient_Amount.csv"):
        hit = NUTRIENT_MAP.get(a["Nutrient_Code"].strip())
        v = a["Nutrient_Amount"].strip()
        if hit and v:
            values.setdefault(a["Food_Code"].strip(), []).append((hit[0], float(v), None, hit[2]))

    measures = {m["Measure_Code"].strip(): clean(m["Measure_Description_and_Unit_EN"])
                for m in table(zf, "Measure_Name.csv")}
    servings = {}
    for m in table(zf, "Measure_Weight_Conversion.csv"):
        if m["Measure_Type_Code"].strip() != SERVING_TYPE:
            continue
        label = measures.get(m["Measure_Code"].strip())
        grams = m["Measure_Weight_Conversion"].strip()
        if label and grams and float(grams) > 0:
            servings.setdefault(m["Food_Code"].strip(), []).append((label, None, float(grams), "g"))

    for f in table(zf, "Food_Name.csv"):
        code = f["Food_Code"].strip()
        food = {
            "id": f"cnf:{code}",
            "source_id": "cnf",
            "source_code": code,
            "name_en": clean(f["Food_Description_EN"]),
            "name_local": clean(f["Food_Description_FR"]) or None,      # French
            "alias": clean(f["Alternate_Description_EN"]) or None,
            "group_en": groups.get(f["CNF_Food_Group_Code"].strip()),
            "description": clean(f["Comment_EN"]) or None,
            "origin_source": origins.get(f["Food_Source_Code"].strip()),
            "origin_code": clean(f["USDA_NDB_Code"]) or None,
        }
        food["search_text"] = search_text(food)
        yield food, values.get(code, []), servings.get(code, [])


LIVE = "data/export/download/remote.db"   # npm run pull: copy of the live D1 database


def load_live(path):
    """Fallback without the zip (user decision 2026-11-13): rebuild the CNF records from the copy
    of the live database (served layout, pipeline/serve_db.py), so CNF stays on the site and goes
    through the same links and names as the other sources.
    - nutrients: the JSON is unpacked; the standard energy is replaced by the source's own figure
      (energy_kcal_source), as in the raw data.
    - origin_code: the live data has no USDA NDB number. A CNF record with exactly one direct
      link to a USDA record gets that record's id as origin_code (link.py rule 1 accepts it)."""
    import json
    import sqlite3
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    src = dict(zip([d[0] for d in db.execute("SELECT * FROM sources WHERE id = 'cnf'").description],
                   db.execute("SELECT * FROM sources WHERE id = 'cnf'").fetchone()))
    cols = ["id", "source_id", "source_code", "name_en", "name_zh", "name_local", "alias", "group_en", "group_zh",
            "subgroup_en", "subgroup_zh", "description", "origin_source"]
    rows = []
    for r in db.execute(f"SELECT {', '.join(cols)}, nutrients, servings, links FROM foods "
                        "WHERE source_id = 'cnf' ORDER BY id"):
        food = {c: (v if v != "" else None) for c, v in zip(cols, r[:len(cols)])}
        nutr, serv, links = (json.loads(x) if x else {} for x in r[len(cols):])
        values = []
        for nid, v in nutr.items():
            if nid in ("energy_kcal", "energy_kcal_source"):
                continue
            d = v if isinstance(v, dict) else {"v": v}
            values.append((nid, d.get("v"), d.get("f"), d.get("m"), d.get("e", 0)))
        e = nutr.get("energy_kcal_source")
        if e is not None:
            d = e if isinstance(e, dict) else {"v": e}
            values.append(("energy_kcal", d.get("v"), d.get("f"), d.get("m"), d.get("e", 0)))
        usda = [k for k in links if k.startswith("usda_")]
        food["origin_code"] = usda[0] if len(usda) == 1 else None
        food["search_text"] = search_text(food)
        rows.append((food, values, [tuple(x) for x in serv]))
    return {k: src[k] for k in ("id", "name", "publisher", "country", "licence", "attribution", "url",
                                "version", "retrieved_at")}, rows


def datasets(root):
    path = root / RAW / FILE
    if not path.exists():
        live = root / LIVE
        if live.exists():
            print(f"  cnf        no {FILE}: records taken from the live copy {LIVE}")
            yield load_live(live)
            return
        print(f"  cnf        skipped: no {FILE} in {RAW}/ (download it by hand, see PROJECT.md 2.10)")
        return
    src = dict(SOURCE, retrieved_at=date.fromtimestamp(path.stat().st_mtime).isoformat())
    yield src, load(path)
