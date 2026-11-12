"""Importer: Hong Kong Centre for Food Safety (CFS) Nutrient Information Inquiry.

Input: cfs_foods.csv, produced by scrape_cfs.py.
CFS republishes values from 5 underlying sources (column source_code A-E).
These are kept in foods.origin_source so duplicates of USDA/FSANZ rows can be
linked later (see food_links).
"""
import csv
import re
from pathlib import Path

from ..common import clean, parse_value, search_text

SOURCE = {
    "id": "cfs",
    "name": "CFS Nutrient Information Inquiry",
    "publisher": "Centre for Food Safety, Food and Environmental Hygiene Department, HKSAR",
    "country": "HK",
    "licence": "See CFS website terms of use",
    "attribution": "食物安全中心 Centre for Food Safety",
    "url": "https://www.cfs.gov.hk/tc_chi/nutrient/fc-search1.php",
    "version": None,
    "retrieved_at": "2025-09-29",
}

ORIGIN = {
    "A": "USDA FoodData Central",
    "B": "China Food Composition (CFC2002)",
    "C": "CFS Food Research Laboratory",
    "D": "Food Standards Australia New Zealand",
    "E": "Thai FCD (Mahidol University)",
}

# Definitions per origin, from the CFS footnotes on fc-nutrientvalue.php (checked 2026-11-12):
#  carbohydrate: FoodData Central (A) and CFC2002 (B) = total carbohydrate;
#                FRL (C), FSANZ (D), Thai FCD (E) = available carbohydrate,
#                except Thai values marked (總量) = total.
#  dietary fibre: CFC2002 (B) = insoluble fibre only; A, C, D = total dietary fibre.
CARB_METHOD = {"A": "total", "B": "total", "C": "available", "D": "available", "E": "available"}
FIBRE_METHOD = {"B": "insoluble"}

COLUMNS = {
    "能量 (千卡)": "energy_kcal",
    "蛋白質 (克)": "protein",
    "碳水化合物 (克)": "carbohydrate",
    "脂肪 (克)": "fat",
    "飽和脂肪 (克)": "fat_sat",
    "反式脂肪 (克)": "fat_trans",
    "膽固醇 (毫克)": "cholesterol",
    "膳食纖維 (克)": "fibre",
    "糖 (克)": "sugars",
    "鈉 (毫克)": "sodium",
    "鉀 (毫克)": "potassium",
    "鈣 (毫克)": "calcium",
    "鎂 (毫克)": "magnesium",
    "磷 (毫克)": "phosphorus",
    "鐵 (毫克)": "iron",
    "鋅 (毫克)": "zinc",
    "銅 (毫克)": "copper",
    "錳 (毫克)": "manganese",
    "維他命 C (毫克)": "vitamin_c",
}


def parse_serving(s):
    # "1小瓶 = 330 克 (1 small bottle=330 grams)" -> ("1 small bottle", "1小瓶", 330.0, "g")
    m = re.match(r"^(.*?)\s*=\s*([\d.]+)\s*(克|毫升)\s*(?:\((.*?)\s*=)?", s or "")
    if not m:
        return None
    return (clean(m.group(4)) or None, clean(m.group(1)) or None,
            float(m.group(2)), "ml" if m.group(3) == "毫升" else "g")


def datasets(root):
    """Yield (SOURCE dict, rows iterator). Same interface as every importer."""
    yield SOURCE, load(root / "cfs_foods.csv")


def load(path):
    """Yield (food, nutrients, servings) tuples.

    food: dict of foods columns; nutrients: list of (nutrient_id, value, flag, method);
    servings: list of (label_en, label_zh, amount, unit).
    """
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    missing = set(COLUMNS) - set(rows[0])
    if missing:
        raise SystemExit(f"cfs: CSV is missing columns {sorted(missing)}")

    for r in rows:
        food = {
            "id": f"cfs:{r['food_id']}",
            "source_id": "cfs",
            "source_code": r["food_id"],
            "name_en": clean(r["name_en"]) or None,
            "name_zh": clean(r["name_zh"]) or None,
            "name_local": None,
            "alias": clean(r["alias"]) or None,
            "group_en": clean(r["group_en"]) or None,
            "group_zh": clean(r["group_zh"]) or None,
            "subgroup_en": clean(r["subgroup_en"]) or None,
            "subgroup_zh": clean(r["subgroup_zh"]) or None,
            "origin_source": ORIGIN.get(r["source_code"]),
        }
        food["search_text"] = search_text(food)

        nutrients = []
        for col, nid in COLUMNS.items():
            parsed = parse_value(r[col])
            if parsed is None:
                continue
            method = None
            if nid == "carbohydrate":
                method = "total" if "(總量)" in r[col] else CARB_METHOD.get(r["source_code"])
            elif nid == "fibre":
                method = FIBRE_METHOD.get(r["source_code"])
            nutrients.append((nid, parsed[0], parsed[1], method))

        servings = []
        sv = parse_serving(r["reference_serving"])
        if sv:
            servings.append(sv)

        yield food, nutrients, servings
