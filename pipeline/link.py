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

 3. Name link: the same food from different sources, by English name (reviewed on a sample
    with the user, 2026-11-12). Weighted word overlap of normalised names, plus:
      - the cooking state must agree (raw / boiled / fried ...),
      - product-form words must agree (flour, juice, oil, powder ...),
      - protein, fat, carbohydrate and water must be roughly similar.
    score >= 0.90 -> 'equivalent'; 0.75-0.90 -> 'similar'; below -> no link.
    Foods already linked as copies are left out.

Not done yet (planned): a species rule (pork vs beef) for lower scores, and the synonym
table for foods without English names (PROJECT.md 4.2).
"""
import math
import re
from collections import Counter, defaultdict

from . import versions

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


# --- rule 3: name link ------------------------------------------------------------
EQUIVALENT_MIN = 0.90
SIMILAR_MIN = 0.75
RARE = 400          # words in more foods than this are too common to find candidates

STATE = {"raw": "raw", "fresh": "raw", "uncooked": "raw",
         "boiled": "boiled", "simmered": "boiled", "stewed": "boiled",
         "steamed": "steamed", "baked": "baked", "roasted": "roasted", "roast": "roasted",
         "fried": "fried", "deep": "fried", "grilled": "grilled", "broiled": "grilled", "microwaved": "microwaved",
         "dried": "dried", "dehydrated": "dried", "canned": "canned", "frozen": "frozen", "cooked": "cooked"}
UKUS = {"aubergine": "eggplant", "courgette": "zucchini", "coriander": "cilantro", "mince": "ground",
        "minced": "ground", "prawn": "shrimp", "prawns": "shrimp", "capsicum": "pepper", "rocket": "arugula",
        "yoghurt": "yogurt", "flavour": "flavor", "wholemeal": "wholewheat", "biscuit": "cookie",
        "chips": "fries", "crisps": "chips", "swede": "rutabaga", "spring": "green", "beetroot": "beet",
        "maize": "corn", "sweetcorn": "corn", "groundnut": "peanut", "lady": "okra"}
STOP = {"and", "or", "with", "the", "of", "a", "in", "all", "type", "types", "regular", "plain", "commercial",
        "average", "composite", "varieties", "ns", "nfs", "as", "to", "from", "added", "no", "without", "salt",
        "includes", "include", "only", "edible", "portion", "flesh", "whole", "unspecified", "purchased", "sample"}

def toks(name):
    out = []
    for w in re.findall(r"[a-z]+", (name or "").lower()):
        w = UKUS.get(w, w)
        if len(w) > 3 and w.endswith("ies"): w = w[:-3] + "y"
        elif len(w) > 3 and w.endswith("oes"): w = w[:-2]
        elif len(w) > 3 and w.endswith("s") and not w.endswith("ss"): w = w[:-1]
        if w not in STOP and w not in STATE: out.append(w)
    return set(out)

def state(name):
    return {STATE[w] for w in re.findall(r"[a-z]+", (name or "").lower()) if w in STATE} or {"raw?"}

foods = {}
FORM = {"flour", "vinegar", "juice", "powder", "oil", "sauce", "soup", "drink", "beverage", "paste", "bread",
        "cake", "pie", "jam", "syrup", "milk", "cream", "cheese", "food", "mix", "bar", "cereal", "noodle",
        "pasta", "sprout", "seed", "leaf", "leaves", "pickle", "pickled", "concentrate", "nectar", "spread",
        "butter", "yolk", "white", "skin", "fat", "liver", "chip", "cracker", "biscuit", "cookie", "candy",
        "salad", "sandwich", "pudding", "dessert", "babyfood", "infant", "formula", "stock", "broth", "gravy"}


def name_tokens(name):
    out = set()
    for w in re.findall(r"[a-z]+", (name or "").lower()):
        w = UKUS.get(w, w)
        if len(w) > 3 and w.endswith("ies"):
            w = w[:-3] + "y"
        elif len(w) > 3 and w.endswith("oes"):
            w = w[:-2]
        elif len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        if w not in STOP and w not in STATE and w not in PART:
            out.add(w)
    return out


# Plant-part words that some sources add (MEXT: "Broccoli, inflorescence, raw").
PART = {"inflorescence", "head", "heads"}
# TFDA English names rarely say "raw"; the state is in the description: "樣品狀態:生".
DESC_STATE = (("樣品狀態:生", "raw"), ("樣品狀態:冷凍", "frozen"))


def cooking_state(name, description=None):
    st = {STATE[w] for w in re.findall(r"[a-z]+", (name or "").lower()) if w in STATE}
    if not st and description:
        st = {state for marker, state in DESC_STATE if description.startswith(marker)}
    return st or {"unstated"}


def plausible(va, vb):
    for k, tol in (("protein", 3), ("fat", 3), ("carbohydrate", 6), ("water", 12)):
        if k in va and k in vb and abs(va[k] - vb[k]) > max(tol, 0.35 * max(va[k], vb[k])):
            return False
    return True


def link_by_name(db):
    foods = {fid: (src, name_tokens(n), cooking_state(n, d))
             for fid, src, n, d in db.execute("SELECT id, source_id, name_en, description FROM foods WHERE name_en IS NOT NULL "
                                           "AND id NOT IN (SELECT food_id FROM food_links)")}
    vals = defaultdict(dict)
    for f, n, v in db.execute("SELECT food_id, nutrient_id, value FROM food_nutrients WHERE value IS NOT NULL "
                              "AND nutrient_id IN ('protein', 'fat', 'carbohydrate', 'water')"):
        vals[f][n] = v
    df = Counter(t for _, ts, _ in foods.values() for t in ts)
    idf = {t: math.log(len(foods) / c) for t, c in df.items()}
    index = defaultdict(list)
    for fid, (_, ts, _) in foods.items():
        for t in ts:
            if df[t] < RARE:
                index[t].append(fid)

    rows = []
    for a in sorted(foods):
        sa, ta, sta = foods[a]
        cands = Counter(b for t in ta if df[t] < RARE for b in index[t] if b > a and foods[b][0] != sa)
        for b, _ in cands.most_common(60):
            sb, tb, stb = foods[b]
            if sta != stb or (ta & FORM) != (tb & FORM):
                continue
            union = sum(idf[t] for t in ta | tb)
            score = sum(idf[t] for t in ta & tb) / union if union else 0
            if score >= SIMILAR_MIN and plausible(vals[a], vals[b]):
                kind = "equivalent" if score >= EQUIVALENT_MIN else "similar"
                rows.append((a, b, kind, round(score, 3), "name+values"))
    return rows


def run(db):
    db.execute("DELETE FROM food_links")
    steps = [
        ("Versions (dated)", versions.link_versions(db)),
        ("CNF -> USDA (code)", link_by_origin_code(db)),
        ("CFS -> USDA (values)", link_by_values(db, "USDA FoodData Central", "f.source_id LIKE 'usda%'")),
        # CFS states FSANZ energy without fibre, converted at 4.2 kJ/kcal, so energy is not compared here.
        ("CFS -> AFCD (values)", link_by_values(db, "Food Standards Australia New Zealand", "f.source_id = 'afcd'",
                                                tuple(k for k in KEY if k != "energy_kcal"))),
    ]
    for label, rows in steps:
        db.executemany("INSERT OR IGNORE INTO food_links (food_id, canonical_id, match_type, confidence, method)"
                       " VALUES (?, ?, ?, ?, ?)", rows)
        print(f"  {label:<22} {len(rows):>5} links  " + ", ".join(f"{n} {k}" for k, n in sorted(Counter(r[2] for r in rows).items())))
    # rule 3 runs after the copies are stored, so it can leave linked copies out
    rows = link_by_name(db)
    db.executemany("INSERT OR IGNORE INTO food_links (food_id, canonical_id, match_type, confidence, method)"
                   " VALUES (?, ?, ?, ?, ?)", rows)
    print(f"  {'Same food (name)':<22} {len(rows):>5} links  " + ", ".join(f"{n} {k}" for k, n in sorted(Counter(r[2] for r in rows).items())))


# --- rule 6: same shown name ---------------------------------------------------------
def carb_total(nutr):
    """Total carbohydrate: 'available' carbohydrate (CFS/FSANZ/MEXT style) does not include
    fibre, 'by difference' / 'total' does. Cloves: 31.6 available + 33.9 fibre = 65.5 total."""
    c = nutr.get("carbohydrate")
    if c is None:
        return None
    value, method = c
    if method in ("available", "available_monosaccharide") and nutr.get("fibre"):
        return value + nutr["fibre"][0]
    return value


def plausible_normalised(a, b):
    """Same food measured by different methods: protein, fat, total carbohydrate and water
    roughly similar (energy is not compared: its formulas differ between countries)."""
    checks = 0
    for k, tol in (("protein", 3), ("fat", 3), ("carbohydrate", 8), ("water", 12)):
        va = carb_total(a) if k == "carbohydrate" else (a.get(k) or (None,))[0]
        vb = carb_total(b) if k == "carbohydrate" else (b.get(k) or (None,))[0]
        if va is None or vb is None:
            continue
        checks += 1
        if abs(va - vb) > max(tol, 0.25 * max(va, vb)):
            return False
    return checks >= 3


def link_same_name(db):
    """Runs after the display and category steps (build_db): main records of different groups
    that are shown with the SAME Chinese name, in the same category, from different sources,
    with plausible values -> 'equivalent' (method 'same_name'). Example: 丁香粉 from CFS/AFCD
    and from MEXT/USDA/CNF (user report 2026-11-12). Groups that share a source are never
    joined: a source's own records with one name are different samples (e.g. two CFS 冬瓜)."""
    nutr = defaultdict(dict)
    for f, n, v, m in db.execute("SELECT food_id, nutrient_id, value, method FROM food_nutrients WHERE value IS NOT NULL "
                                 "AND nutrient_id IN ('protein', 'fat', 'carbohydrate', 'water', 'fibre')"):
        nutr[f][n] = (v, m)
    sources = defaultdict(set)
    for cid, src in db.execute("SELECT cluster_id, source_id FROM foods"):
        sources[cid].add(src)
    by_name = defaultdict(list)
    for fid, zh, cat in db.execute("SELECT id, display_zh, category FROM foods WHERE is_primary = 1 AND display_zh IS NOT NULL"):
        by_name[(zh, cat)].append(fid)
    rows = []
    for ids in by_name.values():
        if len(ids) < 2:
            continue
        ids.sort()
        joined = [ids[0]]                 # merge into the first group, one by one
        srcs = set(sources[ids[0]])
        for b in ids[1:]:
            if srcs & sources[b]:
                continue
            if all(plausible_normalised(nutr[a], nutr[b]) for a in joined):
                rows.append((b, joined[0], "equivalent", 0.8, "same_name"))
                joined.append(b)
                srcs |= sources[b]
    return rows
