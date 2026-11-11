#!/usr/bin/env python3
"""Convert cfs_foods.csv (from scrape_cfs.py) into site/foods.json for the web page.

Nutrient values become numbers where possible; special markers are kept as strings:
  "NA" (no data) -> null, "ND" (not detected) -> "ND", "Trace" -> "Trace".
"12.4 (總量)" (total carbohydrate, Thai FCD) -> 12.4 and the food gets carbTotal=true.
"""
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "cfs_foods.csv"
OUT = ROOT / "site" / "foods.json"

# CSV column -> (key, zh label, en label, unit)
NUTRIENTS = [
    ("能量 (千卡)", "energy", "能量", "Energy", "kcal"),
    ("蛋白質 (克)", "protein", "蛋白質", "Protein", "g"),
    ("碳水化合物 (克)", "carb", "碳水化合物", "Carbohydrate", "g"),
    ("脂肪 (克)", "fat", "脂肪", "Total fat", "g"),
    ("飽和脂肪 (克)", "satfat", "飽和脂肪", "Saturated fat", "g"),
    ("反式脂肪 (克)", "transfat", "反式脂肪", "Trans fat", "g"),
    ("膽固醇 (毫克)", "chol", "膽固醇", "Cholesterol", "mg"),
    ("膳食纖維 (克)", "fibre", "膳食纖維", "Dietary fibre", "g"),
    ("糖 (克)", "sugar", "糖", "Sugars", "g"),
    ("鈉 (毫克)", "sodium", "鈉", "Sodium", "mg"),
    ("鉀 (毫克)", "potassium", "鉀", "Potassium", "mg"),
    ("鈣 (毫克)", "calcium", "鈣", "Calcium", "mg"),
    ("鎂 (毫克)", "magnesium", "鎂", "Magnesium", "mg"),
    ("磷 (毫克)", "phosphorus", "磷", "Phosphorus", "mg"),
    ("鐵 (毫克)", "iron", "鐵", "Iron", "mg"),
    ("鋅 (毫克)", "zinc", "鋅", "Zinc", "mg"),
    ("銅 (毫克)", "copper", "銅", "Copper", "mg"),
    ("錳 (毫克)", "manganese", "錳", "Manganese", "mg"),
    ("維他命 C (毫克)", "vitc", "維他命C", "Vitamin C", "mg"),
]

SOURCES = {
    "A": {"zh": "美國農業部 FoodData Central", "en": "USDA FoodData Central"},
    "B": {"zh": "中國食物成分表 (CFC2002)", "en": "China Food Composition (CFC2002)"},
    "C": {"zh": "食物安全中心食物研究化驗所", "en": "CFS Food Research Laboratory"},
    "D": {"zh": "澳洲新西蘭食品標準局", "en": "Food Standards Australia New Zealand"},
    "E": {"zh": "泰國瑪希隆大學 Thai FCD", "en": "Thai FCD (Mahidol University)"},
}


def value(s):
    s = s.strip()
    if s.upper() in ("", "NA", "N/A"):
        return None
    if s.upper() == "ND":
        return "ND"
    if s.lower() == "trace":
        return "Trace"
    m = re.match(r"^([\d.]+)", s)
    return float(m.group(1)) if m else None


def ref_serving(s):
    # "1小瓶 = 330 克 (1 small bottle=330 grams)" -> {"zh": "1小瓶", "en": "1 small bottle", "g": 330}
    m = re.match(r"^(.*?)\s*=\s*([\d.]+)\s*(克|毫升)\s*(?:\((.*?)\s*=)?", s)
    if not m:
        return None
    return {"zh": m.group(1), "en": (m.group(4) or "").strip(), "g": float(m.group(2)),
            "unit": "ml" if m.group(3) == "毫升" else "g"}


def main():
    rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))
    groups = {}
    foods = []
    for r in rows:
        g = groups.setdefault(r["fg_id"], {"id": r["fg_id"], "zh": r["group_zh"], "en": r["group_en"], "subs": []})
        sub = next((s for s in g["subs"] if s["zh"] == r["subgroup_zh"]), None)
        if sub is None:
            sub = {"id": len(g["subs"]), "zh": r["subgroup_zh"], "en": r["subgroup_en"], "n": 0}
            g["subs"].append(sub)
        sub["n"] += 1
        f = {
            "id": r["food_id"], "g": r["fg_id"], "s": sub["id"],
            "zh": r["name_zh"], "en": r["name_en"], "alias": r["alias"],
            "n": {key: value(r[col]) for col, key, *_ in NUTRIENTS},
        }
        if "(總量)" in r["碳水化合物 (克)"]:
            f["carbTotal"] = True
        ref = ref_serving(r["reference_serving"]) if r["reference_serving"] else None
        if ref:
            f["ref"] = ref
        foods.append(f)

    data = {
        "nutrients": [{"key": k, "zh": zh, "en": en, "unit": u} for _, k, zh, en, u in NUTRIENTS],
        "groups": sorted(groups.values(), key=lambda g: g["en"]),
        "foods": foods,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), "utf-8")
    print(f"{len(foods)} foods, {len(groups)} groups -> {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
