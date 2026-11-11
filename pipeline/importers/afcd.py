"""Importer: Australian Food Composition Database (AFCD), Release 3 (Dec 2025),
Food Standards Australia New Zealand (FSANZ).

Inputs in data/raw/afcd/ (see pipeline/download_afcd.py):
  afcd_r3_nutrient_profiles.xlsx       sheet "All solids & liquids per 100 g" (wide: 1 row per food)
  afcd_r3_food_details.xlsx            food description, derivation
  afcd_r3_food_group_information.xlsx  group and subgroup names

Columns are found by header text; the unit in each header "(g)", "(mg)", "(ug)", "(kJ)"
is checked against the expected unit, so a changed unit stops the build.
Values are plain numbers; a blank cell is no data.

Not imported yet: individual sugars, sugar alcohols, organic acids, contaminant
elements (Al, As, Cd, Pb, Hg, ...), individual fatty acids, amino acids, other
tocopherols/tocotrienols, vitamin D forms, lutein/lycopene, energy without fibre.

Licence: CC BY 4.0 (FSANZ copyright notice).
"""
import re
from datetime import date

from ..common import clean, search_text

RAW = "data/raw/afcd"
SHEET = "All solids & liquids per 100 g"

# Header text (whitespace-normalised, without the unit) -> (our id, header unit, factor, method)
NUTRIENT_MAP = {
    "Energy with dietary fibre, equated": ("energy_kj", "kJ", 1, None),
    "Moisture (water)":                   ("water", "g", 1, None),
    "Protein":                            ("protein", "g", 1, None),
    "Fat, total":                         ("fat", "g", 1, None),
    "Ash":                                ("ash", "g", 1, None),
    "Total dietary fibre":                ("fibre", "g", 1, None),
    "Alcohol":                            ("alcohol", "g", 1, None),
    "Total sugars":                       ("sugars", "g", 1, None),
    "Available carbohydrate, without sugar alcohols": ("carbohydrate_available", "g", 1, None),
    "Calcium (Ca)":                       ("calcium", "mg", 1, None),
    "Chromium (Cr)":                      ("chromium", "ug", 1, None),
    "Copper (Cu)":                        ("copper", "mg", 1, None),
    "Iodine (I)":                         ("iodine", "ug", 1, None),
    "Iron (Fe)":                          ("iron", "mg", 1, None),
    "Magnesium (Mg)":                     ("magnesium", "mg", 1, None),
    "Manganese (Mn)":                     ("manganese", "mg", 1, None),
    "Molybdenum (Mo)":                    ("molybdenum", "ug", 1, None),
    "Phosphorus (P)":                     ("phosphorus", "mg", 1, None),
    "Potassium (K)":                      ("potassium", "mg", 1, None),
    "Selenium (Se)":                      ("selenium", "ug", 1, None),
    "Sodium (Na)":                        ("sodium", "mg", 1, None),
    "Zinc (Zn)":                          ("zinc", "mg", 1, None),
    "Retinol (preformed vitamin A)":      ("retinol", "ug", 1, None),
    "Alpha-carotene":                     ("alpha_carotene", "ug", 1, None),
    "Beta-carotene":                      ("beta_carotene", "ug", 1, None),
    "Cryptoxanthin":                      ("beta_cryptoxanthin", "ug", 1, None),
    "Beta-carotene equivalents (provitamin A)": ("beta_carotene_eq", "ug", 1, None),
    "Vitamin A retinol equivalents":      ("vitamin_a_re", "ug", 1, None),
    "Thiamin (B1)":                       ("vitamin_b1", "mg", 1, None),
    "Riboflavin (B2)":                    ("vitamin_b2", "mg", 1, None),
    "Niacin (B3)":                        ("niacin", "mg", 1, None),
    "Niacin derived equivalents":         ("niacin_eq", "mg", 1, None),
    "Pantothenic acid (B5)":              ("pantothenic_acid", "mg", 1, None),
    "Pyridoxine (B6)":                    ("vitamin_b6", "mg", 1, None),
    "Biotin (B7)":                        ("biotin", "ug", 1, None),
    "Cobalamin (B12)":                    ("vitamin_b12", "ug", 1, None),
    "Total folates":                      ("folate", "ug", 1, None),
    "Vitamin C":                          ("vitamin_c", "mg", 1, None),
    "Vitamin D3 equivalents":             ("vitamin_d", "ug", 1, None),
    "Alpha tocopherol":                   ("alpha_tocopherol", "mg", 1, None),
    "Vitamin E":                          ("vitamin_e_ate", "mg", 1, None),
    "Total saturated fatty acids, equated": ("fat_sat", "g", 1, None),
    "Total monounsaturated fatty acids, equated": ("fat_mono", "g", 1, None),
    "Total polyunsaturated fatty acids, equated": ("fat_poly", "g", 1, None),
    "Total trans fatty acids, imputed":   ("fat_trans", "mg", 0.001, None),
    "Cholesterol":                        ("cholesterol", "mg", 1, None),
    "Caffeine":                           ("caffeine", "mg", 1, None),
}
KJ_PER_KCAL = 4.184

SOURCE = {
    "id": "afcd",
    "name": "Australian Food Composition Database (AFCD), Release 3",
    "publisher": "Food Standards Australia New Zealand (FSANZ)",
    "country": "AU",
    "licence": "CC BY 4.0",
    "attribution": "Food Standards Australia New Zealand (2025). Australian Food Composition Database - Release 3. Canberra: FSANZ.",
    "url": "https://www.foodstandards.gov.au/science-data/food-nutrient-databases/afcd",
    "version": "Release 3 (December 2025)",
}


def norm(h):
    return re.sub(r"\s+", " ", str(h)).strip() if h is not None else ""


def split_header(h):
    """'Protein (g)' -> ('Protein', 'g'); the unit is the LAST parenthesised part."""
    m = re.match(r"^(.*)\s\(([^()]*)\)$", norm(h))
    return (m.group(1).strip(), m.group(2).strip()) if m else (norm(h), None)


def sheet_rows(path, sheet=None):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[sheet] if sheet else wb.worksheets[-1]
    rows = ws.iter_rows(values_only=True)
    for r in rows:
        if r and norm(r[0]) in ("Public Food Key", "Food group ID"):
            header = [norm(c) for c in r]
            break
    else:
        raise SystemExit(f"afcd: header row not found in {path.name}")
    for r in rows:
        if any(c is not None for c in r):
            yield dict(zip(header, r))


def groups(path):
    """'11' -> 'Non-alcoholic beverages', '111' -> 'Tea'."""
    out = {}
    for r in sheet_rows(path):
        gid, gname = r.get("Food group ID"), r.get("Food group name")
        if gid is not None and gname:
            out[str(gid).strip()] = clean(gname)
        m = re.match(r"^(\d{3})\s*-\s*(.+)$", norm(r.get("Inclusions")))
        if m:
            out[m.group(1)] = clean(m.group(2))
    return out


def load(raw):
    grp = groups(raw / "afcd_r3_food_group_information.xlsx")
    details = {r["Public Food Key"]: r for r in sheet_rows(raw / "afcd_r3_food_details.xlsx", "Food details")}

    rows = sheet_rows(raw / "afcd_r3_nutrient_profiles.xlsx", SHEET)
    first = next(rows)
    # Some names appear twice with different units (fatty acids as '%T' of total
    # fatty acids AND as 'g'). Take only the column whose unit is the expected one.
    cols, seen_units = {}, {}
    for h in first:
        name, unit = split_header(h)
        if name in NUTRIENT_MAP:
            nid, want, factor, method = NUTRIENT_MAP[name]
            seen_units.setdefault(name, []).append(unit)
            if unit == want:
                cols[h] = (nid, factor, method)
    found = {split_header(h)[0] for h in cols}
    for name in NUTRIENT_MAP:
        if name not in found:
            raise SystemExit(f"afcd: no {name!r} column with unit {NUTRIENT_MAP[name][1]!r} "
                             f"(found units: {seen_units.get(name)})")

    for r in [first, *rows]:
        key = norm(r.get("Public Food Key"))
        if not key:
            continue
        cls = norm(r.get("Classification"))
        d = details.get(key, {})
        desc = clean(d.get("Food Description"))
        deriv = norm(r.get("Derivation"))
        food = {
            "id": f"afcd:{key}",
            "source_id": "afcd",
            "source_code": key,
            "name_en": clean(r.get("Food Name")),
            "group_en": grp.get(cls[:2]),
            "subgroup_en": grp.get(cls[:3]),
            "description": "; ".join(p for p in (desc, f"Derivation: {deriv}" if deriv else "") if p) or None,
        }
        food["search_text"] = search_text(food)

        values = []
        for h, (nid, factor, method) in cols.items():
            v = r.get(h)
            if v is None or (isinstance(v, str) and not v.strip()):
                continue
            values.append((nid, round(float(v) * factor, 6), None, method))
            if nid == "carbohydrate_available":
                values.append(("carbohydrate", float(v), None, "available"))
            if nid == "energy_kj":
                values.append(("energy_kcal", round(float(v) / KJ_PER_KCAL, 1), None, "from_kj"))
        yield food, values, []


def datasets(root):
    raw = root / RAW
    need = ["afcd_r3_nutrient_profiles.xlsx", "afcd_r3_food_details.xlsx", "afcd_r3_food_group_information.xlsx"]
    if not all((raw / n).exists() for n in need):
        print(f"  afcd       skipped: files missing in {RAW}/ (run python3 -m pipeline.download_afcd)")
        return
    src = dict(SOURCE, retrieved_at=date.fromtimestamp((raw / need[0]).stat().st_mtime).isoformat())
    yield src, load(raw)
