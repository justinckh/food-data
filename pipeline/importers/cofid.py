"""Importer: UK McCance and Widdowson's Composition of Foods Integrated Dataset (CoFID) 2021.

Input: data/raw/cofid/cofid_2021.xlsx (see pipeline/download_cofid.py). Sheets used:
  1.3 Proximates, 1.4 Inorganics, 1.5 Vitamins - one row per food, joined by Food Code.
Columns are found by the identifier row under the header (WATER, PROT, NA, ...);
the unit in the header text is checked.

Food group names: pipeline/importers/cofid_groups.csv, extracted from Appendix B of
the CoFID 2021 user guide.

Value markers:  N  = present, no reliable value -> no row
                Tr = trace                      -> flag TRACE
                blank = no data                 -> no row
Alcoholic beverages (group Q) are given per 100 ml in CoFID, not per 100 g.

Not imported yet: NSP fibre (Englyst), individual sugars, starch, chloride,
tryptophan/60, vitamin fractions, individual fatty acids, phytosterols, organic acids.

Licence: Open Government Licence v3.0.
"""
import csv
import re
from datetime import date
from pathlib import Path

from ..common import clean, search_text

RAW = "data/raw/cofid"
FILE = "cofid_2021.xlsx"

# sheet -> {identifier: (our id, header unit, method)}
NUTRIENT_MAP = {
    "1.3 Proximates": {
        "WATER": ("water", "g", None), "PROT": ("protein", "g", None), "FAT": ("fat", "g", None),
        "CHO": ("carbohydrate", "g", "available_monosaccharide"),
        "KCALS": ("energy_kcal", "kcal", None), "KJ": ("energy_kj", "kJ", None),
        "TOTSUG": ("sugars", "g", None), "ALCO": ("alcohol", "g", None),
        "AOACFIB": ("fibre", "g", None),
        "SATFOD": ("fat_sat", "g", None), "MONOFOD": ("fat_mono", "g", None),
        "POLYFOD": ("fat_poly", "g", None), "FODTRANS": ("fat_trans", "g", None),
        "CHOL": ("cholesterol", "mg", None),
    },
    "1.4 Inorganics": {
        "NA": ("sodium", "mg", None), "K": ("potassium", "mg", None), "CA": ("calcium", "mg", None),
        "MG": ("magnesium", "mg", None), "P": ("phosphorus", "mg", None), "FE": ("iron", "mg", None),
        "CU": ("copper", "mg", None), "ZN": ("zinc", "mg", None), "MN": ("manganese", "mg", None),
        "SE": ("selenium", "ug", None), "I": ("iodine", "ug", None),
    },
    "1.5 Vitamins": {
        "RET": ("retinol", "ug", None), "CAREQU": ("beta_carotene_eq", "ug", None),
        "RETEQU": ("vitamin_a_re", "ug", None), "VITD": ("vitamin_d", "ug", None),
        "VITE": ("vitamin_e_ate", "mg", None), "VITK1": ("vitamin_k1", "ug", None),
        "THIA": ("vitamin_b1", "mg", None), "RIBO": ("vitamin_b2", "mg", None),
        "NIAC": ("niacin", "mg", None), "NIACEQU": ("niacin_eq", "mg", None),
        "VITB6": ("vitamin_b6", "mg", None), "VITB12": ("vitamin_b12", "ug", None),
        "FOLT": ("folate", "ug", None), "PANTO": ("pantothenic_acid", "mg", None),
        "BIOT": ("biotin", "ug", None), "VITC": ("vitamin_c", "mg", None),
    },
}

SOURCE = {
    "id": "cofid",
    "name": "McCance and Widdowson's Composition of Foods Integrated Dataset (CoFID) 2021",
    "publisher": "Public Health England (now Office for Health Improvement and Disparities), UK",
    "country": "GB",
    "licence": "Open Government Licence v3.0",
    "attribution": "Contains public sector information licensed under the Open Government Licence v3.0. "
                   "McCance and Widdowson's The Composition of Foods Integrated Dataset 2021.",
    "url": "https://www.gov.uk/government/publications/composition-of-foods-integrated-dataset-cofid",
    "version": "2021",
}

NUM = re.compile(r"^-?\d+(?:\.\d+)?$")


def header_unit(text):
    m = re.search(r"\(([^()]*)\)\s*$", str(text or ""))
    return m.group(1).strip().replace("µ", "u") if m else None


def parse(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return (float(v), None)
    s = str(v).strip()
    if s in ("", "N"):
        return None
    if s == "Tr":
        return (None, "TRACE")
    if NUM.match(s):
        return (float(s), None)
    raise SystemExit(f"cofid: unexpected value {v!r}")


def groups():
    with open(Path(__file__).with_name("cofid_groups.csv"), encoding="utf-8") as f:
        return {r["code"]: r["name"] for r in csv.DictReader(f)}


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40]


def load(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    grp = groups()
    foods, values, order = {}, {}, []

    # CoFID 2021 reuses at least one food code for two different foods (13-669 is both
    # roasted aubergine and raw watercress). Foods are keyed by (code, name), and a reused
    # code gets the name added to its id so both foods keep a stable, unique id.
    codes = [str(r[0]).strip() for r in list(wb["1.3 Proximates"].iter_rows(values_only=True))[3:] if r[0]]
    reused = {c for c in codes if codes.count(c) > 1}

    for sheet, mapping in NUTRIENT_MAP.items():
        rows = wb[sheet].iter_rows(values_only=True)
        header, ids = next(rows), next(rows)
        next(rows)                                   # row 3: long names
        cols = {}
        for i, ident in enumerate(ids):
            ident = str(ident).strip() if ident else None
            if ident in mapping:
                nid, unit, method = mapping[ident]
                if header_unit(header[i]) != unit:
                    raise SystemExit(f"cofid: {sheet} {ident} unit is {header_unit(header[i])!r}, expected {unit!r}")
                cols[i] = (nid, method)
        missing = set(mapping) - {str(ids[i]).strip() for i in cols}
        if missing:
            raise SystemExit(f"cofid: {sheet} is missing identifiers {sorted(missing)}")

        for r in rows:
            code = str(r[0]).strip() if r[0] else ""
            if not code:
                continue
            name = clean(r[1])
            key = (code, name)
            if key not in foods:
                g = str(r[3]).strip() if r[3] else ""
                per_ml = g.startswith("Q")
                desc = "; ".join(p for p in (clean(r[2]) if isinstance(r[2], str) else "",
                                             "Values per 100 ml" if per_ml else "") if p)
                food = {
                    "id": f"cofid:{code}~{slug(name)}" if code in reused else f"cofid:{code}",
                    "source_id": "cofid",
                    "source_code": f"{code}~{slug(name)}" if code in reused else code,
                    "name_en": name,
                    "group_en": grp.get(g[:1]),
                    "subgroup_en": grp.get(g) if len(g) > 1 else None,
                    "description": desc or None,
                }
                food["search_text"] = search_text(food)
                foods[key] = food
                values[key] = []
                order.append(key)
            for i, (nid, method) in cols.items():
                p = parse(r[i])
                if p is not None:
                    values[key].append((nid, p[0], p[1], method))

    for key in order:
        yield foods[key], values[key], []


def datasets(root):
    path = root / RAW / FILE
    if not path.exists():
        print(f"  cofid      skipped: no {FILE} in {RAW}/ (run python3 -m pipeline.download_cofid)")
        return
    src = dict(SOURCE, retrieved_at=date.fromtimestamp(path.stat().st_mtime).isoformat())
    yield src, load(path)
