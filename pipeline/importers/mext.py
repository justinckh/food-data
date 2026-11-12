"""Importer: Japan MEXT Standard Tables of Food Composition in Japan,
8th revised edition, 2023 supplement (日本食品標準成分表（八訂）増補2023年).

Inputs in data/raw/mext/ (see pipeline/download_mext.py):
  mext_sftc8_2023_main_*.xlsx    main table, chapter 2 data (Japanese names)
  mext_sftc7_2015_english.xlsx   7th edition English table, used ONLY for English
                                 names, matched by 5-digit food number (食品番号)

Columns are found by the INFOODS identifiers in the header row (成分識別子),
not by position.

Value markers (MEXT conventions):
  12.3    analysed value
  (12.3)  estimated / calculated value     -> estimated = 1
  Tr      trace                             -> flag TRACE
  (Tr)    estimated trace                   -> flag TRACE, estimated = 1
  -       not analysed                      -> no row
  blank   no data                           -> no row
  12.3†   footnote mark                     -> mark removed

Not imported yet: fatty acid, amino acid and carbohydrate supplementary tables;
in the main table PROTCAA, FATNLEA, CHOAVLM, CHOAVLDF-, POLYL, OA, beta/gamma/delta
tocopherol and refuse rate.

Licence: Public Data License (Japan) v1.0, compatible with CC BY 4.0.
"""
import re
from datetime import date
from pathlib import Path

from ..common import clean, search_text

RAW = "data/raw/mext"

# INFOODS identifier in the MEXT header -> (our nutrient id, method)
# Units are fixed by MEXT per identifier and match our units for every entry here.
NUTRIENT_MAP = {
    "ENERC_KCAL": ("energy_kcal", None),
    "ENERC":      ("energy_kj", None),
    "WATER":      ("water", None),
    "PROT-":      ("protein", None),          # protein from nitrogen x factor (comparable with other sources)
    "FAT-":       ("fat", None),              # lipid by solvent extraction
    "CHOLE":      ("cholesterol", None),
    "CHOAVL":     ("carbohydrate_available", None),
    "CHOCDF-":    ("carbohydrate", "difference"),
    "FIB-":       ("fibre", None),
    "ASH":        ("ash", None),
    "NA":         ("sodium", None),
    "K":          ("potassium", None),
    "CA":         ("calcium", None),
    "MG":         ("magnesium", None),
    "P":          ("phosphorus", None),
    "FE":         ("iron", None),
    "ZN":         ("zinc", None),
    "CU":         ("copper", None),
    "MN":         ("manganese", None),
    "ID":         ("iodine", None),
    "SE":         ("selenium", None),
    "CR":         ("chromium", None),
    "MO":         ("molybdenum", None),
    "RETOL":      ("retinol", None),
    "CARTA":      ("alpha_carotene", None),
    "CARTB":      ("beta_carotene", None),
    "CRYPXB":     ("beta_cryptoxanthin", None),
    "CARTBEQ":    ("beta_carotene_eq", None),
    "VITA_RAE":   ("vitamin_a_rae", None),
    "VITD":       ("vitamin_d", None),
    "TOCPHA":     ("alpha_tocopherol", None),
    "VITK":       ("vitamin_k", None),
    "THIA":       ("vitamin_b1", None),
    "RIBF":       ("vitamin_b2", None),
    "NIA":        ("niacin", None),
    "NE":         ("niacin_eq", None),
    "VITB6A":     ("vitamin_b6", None),
    "VITB12":     ("vitamin_b12", None),
    "FOL":        ("folate", None),
    "PANTAC":     ("pantothenic_acid", None),
    "BIOT":       ("biotin", None),
    "VITC":       ("vitamin_c", None),
    "ALC":        ("alcohol", None),
    "NACL_EQ":    ("salt_eq", None),
}

# Food groups: Japanese names from the workbook, English names from the MEXT English edition.
GROUPS = {
    "01": ("穀類", "Cereals"), "02": ("いも及びでん粉類", "Potatoes and starches"),
    "03": ("砂糖及び甘味類", "Sugars and sweeteners"), "04": ("豆類", "Pulses"),
    "05": ("種実類", "Nuts and seeds"), "06": ("野菜類", "Vegetables"), "07": ("果実類", "Fruits"),
    "08": ("きのこ類", "Mushrooms"), "09": ("藻類", "Algae"),
    "10": ("魚介類", "Fish, mollusks and crustaceans"), "11": ("肉類", "Meat"), "12": ("卵類", "Eggs"),
    "13": ("乳類", "Milk and milk products"), "14": ("油脂類", "Fats and oils"),
    "15": ("菓子類", "Confectioneries"), "16": ("し好飲料類", "Beverages"),
    "17": ("調味料及び香辛料類", "Seasonings and spices"), "18": ("調理済み流通食品類", "Prepared foods"),
}

SOURCE = {
    "id": "mext",
    "name": "Standard Tables of Food Composition in Japan, 8th ed., 2023 supplement",
    "publisher": "Ministry of Education, Culture, Sports, Science and Technology (MEXT), Japan",
    "country": "JP",
    "licence": "Public Data License (Japan) v1.0 (compatible with CC BY 4.0)",
    "attribution": "文部科学省「日本食品標準成分表（八訂）増補2023年」",
    "url": "https://www.mext.go.jp/a_menu/syokuhinseibun/mext_00001.html",
}

NUM = re.compile(r"^-?\d+(?:\.\d+)?$")


def parse(v):
    """MEXT cell -> (value, flag, estimated) or None for no data."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return (float(v), None, False)
    s = str(v).strip().replace("†", "")
    if s in ("", "-", "*"):
        return None
    est = s.startswith("(") and s.endswith(")")
    if est:
        s = s[1:-1].strip()
    if s == "Tr":
        return (None, "TRACE", est)
    if NUM.match(s):
        return (float(s), None, est)
    raise SystemExit(f"mext: unexpected value {v!r}")


def english_names(path):
    """5-digit food number -> (English name, synonym or None) from the 2015 English table."""
    import openpyxl
    names = {}
    if path is None:
        return names
    ws = openpyxl.load_workbook(path, read_only=True, data_only=True).worksheets[0]
    for r in ws.iter_rows(values_only=True):
        code = str(r[1]).strip() if r[1] is not None else ""
        if not re.fullmatch(r"\d{5}", code) or not isinstance(r[3], str):
            continue
        text = r[3]
        syn = re.findall(r"［\*?Syn\.\s*([^］]+)］", text)
        text = re.sub(r"［[^］]*］", "", text).replace("*", "")
        text = clean(text)
        if not re.search(r"[A-Za-z]", text):      # the 2015 table has "-" for a few foods
            continue
        names[code] = (text, clean(", ".join(syn)) or None)
    return names


def load(main_path, english_path):
    import openpyxl
    en = english_names(english_path)
    ws = openpyxl.load_workbook(main_path, read_only=True, data_only=True)["表全体"]
    rows = ws.iter_rows(values_only=True)

    header = None
    for r in rows:
        if r[3] == "成分識別子":
            header = [str(c).strip() if c is not None else None for c in r]
            break
    if header is None:
        raise SystemExit("mext: header row with 成分識別子 not found")
    cols = {ident: i for i, ident in enumerate(header) if ident in NUTRIENT_MAP}
    missing = set(NUTRIENT_MAP) - set(cols)
    if missing:
        raise SystemExit(f"mext: identifiers missing from the workbook: {sorted(missing)}")
    remark_col = header.index("NACL_EQ") + 1   # 備考 (remarks) column follows NACL_EQ

    for r in rows:
        code = str(r[1]).strip() if r[1] is not None else ""
        if not re.fullmatch(r"\d{5}", code):
            continue
        group = str(r[0]).strip().zfill(2)
        g_ja, g_en = GROUPS.get(group, (None, None))
        name_en, syn = en.get(code, (None, None))
        food = {
            "id": f"mext:{code}",
            "source_id": "mext",
            "source_code": code,
            "name_en": name_en,
            "name_local": clean(r[3]),
            "alias": syn,
            "group_en": g_en,
            "subgroup_en": None,
            "description": clean(r[remark_col]) if isinstance(r[remark_col], str) else None,
        }
        # group_zh: Japanese group names are kanji-heavy and readable to Chinese users,
        # but they are Japanese - keep them out of group_zh and in the search text only.
        food["search_text"] = search_text(dict(food, group_zh=g_ja))

        values = []
        for ident, i in cols.items():
            p = parse(r[i])
            if p is None:
                continue
            nid, method = NUTRIENT_MAP[ident]
            values.append((nid, p[0], p[1], method, p[2]))
        yield food, values, []


def datasets(root):
    raw = root / RAW
    mains = sorted(raw.glob("mext_sftc8_*_main_*.xlsx"))
    if not mains:
        print(f"  mext       skipped: no mext_sftc8_*_main_*.xlsx in {RAW}/ (run python3 -m pipeline.download_mext)")
        return
    main = mains[-1]
    english = next(iter(sorted(raw.glob("mext_sftc7_*_english.xlsx"))), None)
    m = re.search(r"_(\d{8})\.xlsx$", main.name)
    version = f"2023 supplement, data update {m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]}" if m else "2023 supplement"
    src = dict(SOURCE, version=version, retrieved_at=date.fromtimestamp(main.stat().st_mtime).isoformat())
    yield src, load(main, english)
