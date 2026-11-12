"""Importer: USDA FoodData Central (FDC) - Foundation Foods and SR Legacy.

Input: the official FDC CSV zip files in data/raw/usda/ (see pipeline/download_usda.py).
The zips are read in place; nothing is extracted to disk.

Files used inside each zip (FDC bulk CSV format):
  food.csv            fdc_id, data_type, description, food_category_id, ...
  food_category.csv   id, code, description
  nutrient.csv        id, name, unit_name, nutrient_nbr, ...
  food_nutrient.csv   fdc_id, nutrient_id, amount, ...
  food_portion.csv    fdc_id, amount, measure_unit_id, portion_description, modifier, gram_weight, ...
  measure_unit.csv    id, name

Licence: FDC data is public domain (CC0 1.0).
"""
import csv
import io
import re
import sys
import zipfile
from datetime import date
from pathlib import Path

from ..common import clean, search_text

RAW = "data/raw/usda"

DATASETS = {
    # source id : (zip filename pattern, FDC data_type to keep, source metadata)
    "usda_fnd": ("*foundation*csv*.zip", "foundation_food", "USDA FoodData Central - Foundation Foods"),
    "usda_sr": ("*sr_legacy*csv*.zip", "sr_legacy_food", "USDA FoodData Central - SR Legacy"),
}

# Our nutrient id -> FDC nutrient_nbr candidates, best first, with the unit we expect.
# Matching on nutrient_nbr (stable across releases) and checking the unit, so a
# kJ energy row or a different sugar definition can never slip in silently.
NUTRIENT_MAP = {
    "energy_kcal":  (["208", "958", "957"], "KCAL"),   # 958/957 = Atwater specific/general (Foundation)
    "protein":      (["203"], "G"),
    "carbohydrate": (["205", "205.2"], "G"),           # by difference, else by summation (Foundation)
    "fat":          (["204"], "G"),
    "fat_sat":      (["606"], "G"),
    "fat_trans":    (["605"], "G"),
    "cholesterol":  (["601"], "MG"),
    "fibre":        (["291"], "G"),
    "sugars":       (["269", "269.3"], "G"),
    "sodium":       (["307"], "MG"),
    "potassium":    (["306"], "MG"),
    "calcium":      (["301"], "MG"),
    "magnesium":    (["304"], "MG"),
    "phosphorus":   (["305"], "MG"),
    "iron":         (["303"], "MG"),
    "zinc":         (["309"], "MG"),
    "copper":       (["312"], "MG"),
    "manganese":    (["315"], "MG"),
    "vitamin_c":    (["401"], "MG"),
    "water":        (["255"], "G"),     # added 2026-11-12 for the energy standard (pipeline/serve_db.py)
    "ash":          (["207"], "G"),
    "alcohol":      (["221"], "G"),
}

# Record which definition was used when it is not the first choice.
METHOD = {
    ("energy_kcal", 1): "atwater_specific",
    ("energy_kcal", 2): "atwater_general",
    ("carbohydrate", 0): "difference",
    ("carbohydrate", 1): "summation",
}


class Zip:
    """Read CSVs from an FDC zip, whatever folder name the release uses inside."""

    def __init__(self, path):
        self.zf = zipfile.ZipFile(path)
        self.names = {Path(n).name: n for n in self.zf.namelist() if n.endswith(".csv")}

    def rows(self, name, required=True):
        if name not in self.names:
            if required:
                raise SystemExit(f"usda: {name} not found in {self.zf.filename}")
            return iter(())
        fh = io.TextIOWrapper(self.zf.open(self.names[name]), encoding="utf-8-sig", newline="")
        return csv.DictReader(fh)


def release_date(path):
    m = re.search(r"(\d{4}-\d{2}(?:-\d{2})?)", path.name)
    return m.group(1) if m else None


def find_zip(root, pattern):
    """Newest release (by file-name date) that has the core tables."""
    for path in sorted((root / RAW).glob(pattern), reverse=True):
        names = {Path(n).name for n in zipfile.ZipFile(path).namelist()}
        if {"food.csv", "food_nutrient.csv", "nutrient.csv"} <= names:
            return path
        print(f"    warning: {path.name} has no food.csv/food_nutrient.csv - ignored", file=sys.stderr)
    return None


def resolve_nutrients(z):
    """Map FDC nutrient.id -> our nutrient id, picking the best candidate per food later."""
    by_nbr = {}
    for r in z.rows("nutrient.csv"):
        by_nbr.setdefault(r["nutrient_nbr"].strip(), []).append(r)
    fdc_to_ours = {}   # fdc nutrient id -> (our id, priority)
    for ours, (nbrs, unit) in NUTRIENT_MAP.items():
        for prio, nbr in enumerate(nbrs):
            for r in by_nbr.get(nbr, []):
                if r["unit_name"].strip().upper() == unit:
                    fdc_to_ours[r["id"]] = (ours, prio)
    found = {o for o, _ in fdc_to_ours.values()}
    lost = set(NUTRIENT_MAP) - found
    if lost:
        print(f"    warning: no FDC nutrient found for {sorted(lost)}", file=sys.stderr)
    return fdc_to_ours


def portion_label(r, units):
    """'1', 'cup', '', 'chopped' -> '1 cup chopped'. FDC unit 'undetermined' (SR Legacy) is dropped."""
    amount = clean(r.get("amount"))
    if amount.endswith(".0"):
        amount = amount[:-2]
    unit = units.get((r.get("measure_unit_id") or "").strip(), "")
    if unit.lower() == "undetermined":
        unit = ""
    parts = [amount, unit, clean(r.get("portion_description")), clean(r.get("modifier"))]
    return " ".join(p for p in parts if p) or None


def load_dataset(path, data_type, source_id):
    z = Zip(path)
    cats = {r["id"]: clean(r["description"]) for r in z.rows("food_category.csv", required=False)}
    units = {r["id"]: clean(r["name"]) for r in z.rows("measure_unit.csv", required=False)}
    fdc_to_ours = resolve_nutrients(z)

    # NDB number (the pre-FDC USDA code) per fdc_id; other publishers (e.g. CNF) cite it.
    ndb = {}
    for name in ("sr_legacy_food.csv", "foundation_food.csv"):
        for r in z.rows(name, required=False):
            if (r.get("NDB_number") or "").strip():
                ndb[r["fdc_id"].strip()] = r["NDB_number"].strip().lstrip("0")

    foods = {}
    for r in z.rows("food.csv"):
        if r["data_type"].strip() != data_type:
            continue   # Foundation zips also hold sample/sub-sample records
        fid = r["fdc_id"].strip()
        food = {
            "id": f"{source_id}:{fid}",
            "source_id": source_id,
            "source_code": fid,
            "name_en": clean(r["description"]) or None,
            "name_zh": None,
            "name_local": None,
            "alias": None,
            "group_en": cats.get(r.get("food_category_id", "").strip()),
            "group_zh": None,
            "subgroup_en": None,
            "subgroup_zh": None,
            "origin_source": None,
        }
        if fid in ndb:
            food["codes"] = [("usda_ndb", ndb[fid])]
        food["search_text"] = search_text(food)
        foods[fid] = food

    best = {}   # (fdc_id, our id) -> (priority, value)
    for r in z.rows("food_nutrient.csv"):
        fid = r["fdc_id"].strip()
        hit = fdc_to_ours.get(r["nutrient_id"].strip())
        if fid not in foods or not hit or not r["amount"].strip():
            continue
        ours, prio = hit
        key = (fid, ours)
        if key not in best or prio < best[key][0]:
            best[key] = (prio, float(r["amount"]))
    values = {}
    for (fid, ours), (prio, v) in best.items():
        values.setdefault(fid, []).append((ours, v, None, METHOD.get((ours, prio))))

    servings = {}
    for r in z.rows("food_portion.csv", required=False):
        fid = r["fdc_id"].strip()
        if fid not in foods or not r["gram_weight"].strip():
            continue
        servings.setdefault(fid, []).append((portion_label(r, units), None, float(r["gram_weight"]), "g"))

    for fid, food in foods.items():
        yield food, values.get(fid, []), servings.get(fid, [])


def datasets(root):
    """Yield (SOURCE dict, rows iterator) for each FDC dataset found in data/raw/usda/."""
    for source_id, (pattern, data_type, name) in DATASETS.items():
        path = find_zip(root, pattern)
        if path is None:
            print(f"  {source_id:<10} skipped: no {pattern} in {RAW}/ (run python3 -m pipeline.download_usda)")
            continue
        source = {
            "id": source_id,
            "name": name,
            "publisher": "U.S. Department of Agriculture, Agricultural Research Service",
            "country": "US",
            "licence": "Public domain (CC0 1.0)",
            "attribution": "U.S. Department of Agriculture, Agricultural Research Service. FoodData Central.",
            "url": "https://fdc.nal.usda.gov/",
            "version": release_date(path),
            "retrieved_at": date.fromtimestamp(path.stat().st_mtime).isoformat(),
        }
        yield source, load_dataset(path, data_type, source_id)
