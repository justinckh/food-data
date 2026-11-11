"""Shared pieces for every importer: the master nutrient list, value parsing,
and the search-text builder.

Rules:
- Every importer maps its source columns to ids in NUTRIENTS. Add new nutrients
  here (never rename an existing id - links and exports depend on them).
- search_text() is the ONLY place that decides what text describes a food.
  The FTS index uses it now; the embedding script will use the same text later.
"""
import re
import unicodedata

# id, infoods_tag (only where the meaning is certain), name_en, name_zh, unit
NUTRIENTS = [
    ("energy_kcal",  "ENERC_KCAL", "Energy",        "能量",       "kcal"),
    ("protein",      "PROCNT",     "Protein",       "蛋白質",     "g"),
    # Carbohydrate definitions differ between sources (available vs total vs by
    # difference). Kept as one id; food_nutrients.method records 'total' when known.
    ("carbohydrate", None,         "Carbohydrate",  "碳水化合物", "g"),
    ("fat",          "FAT",        "Total fat",     "脂肪",       "g"),
    ("fat_sat",      "FASAT",      "Saturated fat", "飽和脂肪",   "g"),
    ("fat_trans",    "FATRN",      "Trans fat",     "反式脂肪",   "g"),
    ("cholesterol",  "CHOLE",      "Cholesterol",   "膽固醇",     "mg"),
    ("fibre",        None,         "Dietary fibre", "膳食纖維",   "g"),
    ("sugars",       "SUGAR",      "Sugars",        "糖",         "g"),
    ("sodium",       "NA",         "Sodium",        "鈉",         "mg"),
    ("potassium",    "K",          "Potassium",     "鉀",         "mg"),
    ("calcium",      "CA",         "Calcium",       "鈣",         "mg"),
    ("magnesium",    "MG",         "Magnesium",     "鎂",         "mg"),
    ("phosphorus",   "P",          "Phosphorus",    "磷",         "mg"),
    ("iron",         "FE",         "Iron",          "鐵",         "mg"),
    ("zinc",         "ZN",         "Zinc",          "鋅",         "mg"),
    ("copper",       "CU",         "Copper",        "銅",         "mg"),
    ("manganese",    "MN",         "Manganese",     "錳",         "mg"),
    ("vitamin_c",    "VITC",       "Vitamin C",     "維他命C",    "mg"),
]
NUTRIENT_IDS = {n[0] for n in NUTRIENTS}


def parse_value(raw):
    """Source cell -> (value, flag). Returns None when there is no data ('NA', empty).

    '12.4'        -> (12.4, None)
    'ND'          -> (None, 'ND')
    'Trace'       -> (None, 'TRACE')
    '12.4 (總量)' -> (12.4, None)   caller checks the suffix for method
    """
    s = (raw or "").strip()
    if s.upper() in ("", "NA", "N/A", "-"):
        return None
    if s.upper() == "ND":
        return (None, "ND")
    if s.lower() in ("trace", "tr"):
        return (None, "TRACE")
    m = re.match(r"^-?\d+(?:\.\d+)?", s)
    return (float(m.group(0)), None) if m else None


def clean(s):
    """Normalise whitespace and Unicode width (full-width -> half-width digits/latin)."""
    if not s:
        return ""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s)).strip()


def search_text(food):
    """Build the text that describes a food for search (FTS now, embeddings later).

    Uses names in every language, aliases, and group names. Never nutrient values -
    numeric questions are answered with SQL, not text search.
    """
    parts = [
        food.get("name_en"), food.get("name_zh"), food.get("name_local"),
        food.get("alias"),
        food.get("subgroup_en"), food.get("subgroup_zh"),
        food.get("group_en"), food.get("group_zh"),
    ]
    seen, out = set(), []
    for p in parts:
        p = clean(p)
        if p and p.lower() not in seen:
            seen.add(p.lower())
            out.append(p)
    return " | ".join(out)
