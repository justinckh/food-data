"""Link layer: find foods that are the same record republished by another source.

Runs at the end of every build (pipeline/build_db.py), on the whole database.
Raw rows are never changed or deleted; results go to food_links:
  food_id      = the copy (the republishing source)
  canonical_id = the original
  match_type   = 'exact_copy' (same values: hide the copy by default)
               | 'equivalent' (same food, values differ: show both)

Rules, strongest first:
 1. Code link: CNF foods that cite a USDA NDB number (foods.origin_code) -> the USDA
    record with that NDB number (food_codes 'usda_ndb'). exact_copy if the key nutrients
    agree, else equivalent.
 2. Value link: CFS foods whose data came from USDA (code A) or FSANZ (code D) carry no
    code; they are matched by identical key-nutrient values. A unique match is an
    exact_copy. Several matches are settled by name similarity, or left unlinked.

Not done yet (planned): fuzzy 'equivalent' links across countries by name/group, and
the synonym table (PROJECT.md 4.2).
"""
import re
from collections import defaultdict

KEY = ("protein", "fat", "carbohydrate", "sodium", "calcium", "iron", "potassium", "energy_kcal")
MIN_COMMON = 4     # nutrients both foods must have to compare at all
MIN_NONZERO = 2    # agreeing non-zero values needed - else every oil or sugar "matches"


def close(a, b):
    return abs(a - b) <= max(0.011, 0.015 * abs(b))


def compare(a, b, keys=KEY):
    """-> (common, agreeing, agreeing_nonzero) over the key nutrients."""
    common = [k for k in keys if k in a and k in b]
    agree = [k for k in common if close(a[k], b[k])]
    return len(common), len(agree), sum(1 for k in agree if abs(b[k]) > 0.05)


def same_values(a, b, keys=KEY, allow_off=0):
    common, agree, nonzero = compare(a, b, keys)
    return common >= MIN_COMMON and nonzero >= MIN_NONZERO and agree >= common - allow_off


def words(name):
    return set(re.findall(r"[a-z]+", (name or "").lower())) - {"and", "or", "with", "the", "of", "raw", "all"}


def name_sim(a, b):
    wa, wb = words(a), words(b)
    return len(wa & wb) / len(wa | wb) if wa and wb else 0.0


def key_values(db, where, args=()):
    vals = defaultdict(dict)
    q = (f"SELECT n.food_id, n.nutrient_id, n.value FROM food_nutrients n JOIN foods f ON f.id = n.food_id "
         f"WHERE n.value IS NOT NULL AND n.nutrient_id IN ({','.join('?' * len(KEY))}) AND {where}")
    for fid, nid, v in db.execute(q, (*KEY, *args)):
        vals[fid][nid] = v
    return vals


def link_by_origin_code(db):
    usda = dict(db.execute("SELECT code, food_id FROM food_codes WHERE scheme = 'usda_ndb'"))
    pairs = [(fid, usda.get(code.lstrip("0")))
             for fid, code in db.execute("SELECT id, origin_code FROM foods WHERE source_id = 'cnf' AND origin_code IS NOT NULL")]
    pairs = [(c, u) for c, u in pairs if u]
    vals = key_values(db, "(f.source_id = 'cnf' OR f.source_id LIKE 'usda%')")
    rows = []
    for copy, orig in pairs:
        if same_values(vals[copy], vals[orig]):
            rows.append((copy, orig, "exact_copy", 1.0, "origin_code+values"))
        else:
            rows.append((copy, orig, "equivalent", 0.9, "origin_code"))
    return rows


def link_by_values(db, origin_label, target_where, keys=KEY):
    copies = [r[0] for r in db.execute("SELECT id FROM foods WHERE source_id = 'cfs' AND origin_source = ?", (origin_label,))]
    vals = key_values(db, f"(f.source_id = 'cfs' OR {target_where})")
    names = dict(db.execute("SELECT id, name_en FROM foods"))
    targets = [f for f in vals if not f.startswith("cfs:")]

    # bucket targets by rounded protein so each copy is compared with few candidates
    buckets = defaultdict(list)
    for t in targets:
        if "protein" in vals[t]:
            buckets[round(vals[t]["protein"])].append(t)

    rows = []
    for c in copies:
        a = vals.get(c, {})
        if "protein" not in a:
            continue
        p = round(a["protein"])
        cands = [t for d in (-1, 0, 1) for t in buckets.get(p + d, []) if same_values(a, vals[t], keys)]
        if len(cands) == 1:
            rows.append((c, cands[0], "exact_copy", 0.95, "values"))
        elif len(cands) > 1:
            ranked = sorted(((name_sim(names[c], names[t]), t) for t in cands), reverse=True)
            if ranked[0][0] >= 0.3 and ranked[0][0] - ranked[1][0] >= 0.15:
                rows.append((c, ranked[0][1], "exact_copy", 0.85, "values+name"))
    return rows


def run(db):
    db.execute("DELETE FROM food_links")
    steps = [
        ("CNF -> USDA (code)", link_by_origin_code(db)),
        ("CFS -> USDA (values)", link_by_values(db, "USDA FoodData Central", "f.source_id LIKE 'usda%'")),
        # CFS states FSANZ energy without fibre, converted at 4.2 kJ/kcal, so energy is not compared here.
        ("CFS -> AFCD (values)", link_by_values(db, "Food Standards Australia New Zealand", "f.source_id = 'afcd'",
                                                tuple(k for k in KEY if k != "energy_kcal"))),
    ]
    for label, rows in steps:
        db.executemany("INSERT OR IGNORE INTO food_links (food_id, canonical_id, match_type, confidence, method)"
                       " VALUES (?, ?, ?, ?, ?)", rows)
        exact = sum(1 for r in rows if r[2] == "exact_copy")
        print(f"  {label:<22} {len(rows):>5} links  ({exact} exact_copy, {len(rows) - exact} equivalent)")
