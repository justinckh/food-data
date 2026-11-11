"""Importer: Taiwan Food and Drug Administration (TFDA) food nutrient composition.

Dataset 8543 "食品營養成分資料集", from https://data.fda.gov.tw (export id 20, CSV).
Input: the newest data/raw/tfda/*.csv.zip (see pipeline/download_tfda.py). Read in place.

The CSV is long format: one row per food per nutrient (~104 nutrients x ~2,200 foods).
Columns: 食品分類, 資料類別, 整合編號, 樣品名稱, 俗名, 樣品英文名稱, 內容物描述, 廢棄率,
         分析項分類, 分析項, 含量單位, 每100克含量, 樣本數, 標準差, 每單位含量, 每單位重, 每單位重含量

Not imported yet (kept in the raw file): individual amino acids, individual fatty
acids, individual sugars, IU duplicates of vitamins A/D, other tocopherols, vitamin K2,
P/M/S ratio, refuse rate (廢棄率), sample count and standard deviation.
"""
import csv
import io
import re
import zipfile
from datetime import date
from pathlib import Path

from ..common import clean, search_text

RAW = "data/raw/tfda"

# 分析項 -> (our nutrient id, expected source unit, factor to our unit, method)
NUTRIENT_MAP = {
    "熱量":                 ("energy_kcal", "kcal", 1, None),
    "修正熱量":             ("energy_kcal_adjusted", "kcal", 1, None),
    "水分":                 ("water", "g", 1, None),
    "灰分":                 ("ash", "g", 1, None),
    "粗蛋白":               ("protein", "g", 1, None),
    "粗脂肪":               ("fat", "g", 1, None),
    "飽和脂肪":             ("fat_sat", "g", 1, None),
    "總碳水化合物":         ("carbohydrate", "g", 1, "total"),
    "膳食纖維":             ("fibre", "g", 1, None),
    "糖質總量":             ("sugars", "g", 1, None),
    "反式脂肪":             ("fat_trans", "mg", 0.001, None),
    "膽固醇":               ("cholesterol", "mg", 1, None),
    "酒精含量":             ("alcohol", "g", 1, None),
    "鈉":                   ("sodium", "mg", 1, None),
    "鉀":                   ("potassium", "mg", 1, None),
    "鈣":                   ("calcium", "mg", 1, None),
    "鎂":                   ("magnesium", "mg", 1, None),
    "磷":                   ("phosphorus", "mg", 1, None),
    "鐵":                   ("iron", "mg", 1, None),
    "鋅":                   ("zinc", "mg", 1, None),
    "銅":                   ("copper", "mg", 1, None),
    "錳":                   ("manganese", "mg", 1, None),
    "脂肪酸M總量":          ("fat_mono", "mg", 0.001, None),
    "脂肪酸P總量":          ("fat_poly", "mg", 0.001, None),
    "視網醇當量(RE)":       ("vitamin_a_re", "ug", 1, None),
    "視網醇":               ("retinol", "ug", 1, None),
    "β-胡蘿蔔素":           ("beta_carotene", "ug", 1, None),
    "α-胡蘿蔔素":           ("alpha_carotene", "ug", 1, None),
    "維生素B1":             ("vitamin_b1", "mg", 1, None),
    "維生素B2":             ("vitamin_b2", "mg", 1, None),
    "菸鹼素":               ("niacin", "mg", 1, None),
    "維生素B6":             ("vitamin_b6", "mg", 1, None),
    "維生素B12":            ("vitamin_b12", "ug", 1, None),
    "葉酸":                 ("folate", "ug", 1, None),
    "維生素C":              ("vitamin_c", "mg", 1, None),
    "維生素D總量(ug)":      ("vitamin_d", "ug", 1, None),
    "α-維生素E當量(α-TE)":  ("vitamin_e_ate", "mg", 1, None),
    "α-生育酚":             ("alpha_tocopherol", "mg", 1, None),
    "維生素K1":             ("vitamin_k1", "ug", 1, None),
}

# Our English translation of the 18 TFDA food groups.
GROUP_EN = {
    "穀物類": "Cereals and grains", "澱粉類": "Starchy foods", "堅果及種子類": "Nuts and seeds",
    "水果類": "Fruits", "蔬菜類": "Vegetables", "藻類": "Algae and seaweeds", "菇類": "Mushrooms",
    "豆類": "Legumes", "肉類": "Meat", "魚貝類": "Fish and shellfish", "蛋類": "Eggs",
    "乳品類": "Dairy", "油脂類": "Fats and oils", "糖類": "Sugars", "飲料類": "Beverages",
    "調味料及香辛料類": "Seasonings and spices", "糕餅點心類": "Cakes, pastries and snacks",
    "加工調理食品及其他類": "Processed and prepared foods, other",
}

SOURCE = {
    "id": "tfda",
    "name": "TFDA Food Nutrient Composition Database (食品營養成分資料集)",
    "publisher": "Food and Drug Administration, Ministry of Health and Welfare, Taiwan",
    "country": "TW",
    "licence": "Open Government Data License, version 1.0 (Taiwan)",
    "attribution": "衛生福利部食品藥物管理署 食品營養成分資料集",
    "url": "https://data.fda.gov.tw/",
    "version": None,
}

NUMBER = re.compile(r"^-?\d+(?:\.\d+)?$")


def find_zip(root):
    hits = sorted((root / RAW).glob("*.csv.zip"), key=lambda p: p.stat().st_mtime)
    return hits[-1] if hits else None


def load(path):
    zf = zipfile.ZipFile(path)
    name = next(n for n in zf.namelist() if n.endswith(".csv"))
    reader = csv.DictReader(io.TextIOWrapper(zf.open(name), encoding="utf-8-sig", newline=""))

    foods, values, servings, order = {}, {}, {}, []
    for r in reader:
        code = r["整合編號"].strip()
        if code not in foods:
            group_zh = clean(r["食品分類"]) or None
            food = {
                "id": f"tfda:{code}",
                "source_id": "tfda",
                "source_code": code,
                "name_en": clean(r["樣品英文名稱"]) or None,
                "name_zh": clean(r["樣品名稱"]) or None,
                "alias": clean(r["俗名"]) or None,
                "group_en": GROUP_EN.get(group_zh),
                "group_zh": group_zh,
                "description": clean(r["內容物描述"]) or None,
            }
            food["search_text"] = search_text(food)
            foods[code] = food
            values[code] = []
            order.append(code)

        item = r["分析項"].strip()
        if item == "熱量":
            m = re.match(r"^([\d.]+)\s*克$", r["每單位重"].strip())
            if m and float(m.group(1)) > 0:
                servings[code] = [("1 unit", "每單位", float(m.group(1)), "g")]

        hit = NUTRIENT_MAP.get(item)
        if not hit:
            continue
        nid, unit, factor, method = hit
        if r["含量單位"].strip() != unit:
            raise SystemExit(f"tfda: {item} unit is {r['含量單位']!r}, expected {unit!r} - check the mapping")
        raw = r["每100克含量"].strip()
        if not raw:
            continue           # blank = no data
        if not NUMBER.match(raw):
            raise SystemExit(f"tfda: unexpected value {raw!r} for {code} {item}")
        values[code].append((nid, round(float(raw) * factor, 6), None, method))

    for code in order:
        yield foods[code], values[code], servings.get(code, [])


def datasets(root):
    path = find_zip(root)
    if path is None:
        print(f"  tfda       skipped: no *.csv.zip in {RAW}/ (run python3 -m pipeline.download_tfda)")
        return
    src = dict(SOURCE, retrieved_at=date.fromtimestamp(path.stat().st_mtime).isoformat())
    yield src, load(path)
