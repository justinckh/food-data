"""Build the SERVED database (what goes to Cloudflare D1) from the master data/food.db.

Run from the project root:   python3 -m pipeline.serve_db      -> data/export/served.db

Why a separate shape: D1 counts every written ROW (and every index entry), not bytes.
The master copy keeps one row per food per nutrient (767k rows; a full upload was ~2.6M
row writes). The served copy has ONE row per food: all nutrients, servings and the
food-page lists (other records of the same food, similar foods, related foods) are
stored as JSON text in that row. A full upload is ~26k food rows; reads per food page
drop from ~30 rows per record to 1.

Served tables: sources (+ foods count), nutrients, categories and subcategories (+ n main records,
n_records all records), foods.
Key nutrients (KEY_NUTRIENTS) are also normal columns, for list rows and sorting.
"""
import bisect
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MASTER = ROOT / "data" / "food.db"
SERVED = ROOT / "data" / "export" / "served.db"

KEY_NUTRIENTS = ["energy_kcal", "protein", "fat", "carbohydrate", "sugars", "fibre", "sodium"]
TEXT_COLS = ["id", "source_id", "source_code", "name_en", "name_zh", "name_local", "alias",
             "group_en", "group_zh", "subgroup_en", "subgroup_zh", "description", "origin_source",
             "search_text", "cluster_id", "is_primary", "display_zh", "display_en", "sample_note", "category", "zh_mt", "subcategory"]
N_SIMILAR = N_RELATED = 8

SCHEMA = f"""
CREATE TABLE sources (id TEXT PRIMARY KEY, name TEXT NOT NULL, publisher TEXT, country TEXT, licence TEXT,
    attribution TEXT, url TEXT, version TEXT, retrieved_at TEXT, foods INTEGER NOT NULL);
CREATE TABLE nutrients (id TEXT PRIMARY KEY, infoods_tag TEXT, name_en TEXT NOT NULL, name_zh TEXT,
    unit TEXT NOT NULL, sort_order INTEGER NOT NULL);
CREATE TABLE categories (id TEXT PRIMARY KEY, name_zh TEXT NOT NULL, name_en TEXT NOT NULL,
    sort_order INTEGER NOT NULL, n INTEGER NOT NULL, n_records INTEGER);
CREATE TABLE subcategories (id TEXT PRIMARY KEY, category TEXT NOT NULL, name_zh TEXT NOT NULL,
    name_en TEXT NOT NULL, sort_order INTEGER NOT NULL, n INTEGER NOT NULL, n_records INTEGER NOT NULL);
CREATE TABLE foods (
    id TEXT PRIMARY KEY, source_id TEXT NOT NULL, source_code TEXT NOT NULL, name_en TEXT, name_zh TEXT,
    name_local TEXT, alias TEXT, group_en TEXT, group_zh TEXT, subgroup_en TEXT, subgroup_zh TEXT,
    description TEXT, origin_source TEXT, search_text TEXT NOT NULL, cluster_id TEXT NOT NULL,
    is_primary INTEGER NOT NULL, display_zh TEXT, display_en TEXT, sample_note TEXT, category TEXT,
    zh_mt INTEGER NOT NULL,          -- 1 = display_zh is a machine translation
    subcategory TEXT,                -- e.g. 'meat.beef' (pipeline/subcategories.py)
    n_sources INTEGER NOT NULL,      -- sources with a record in this food's group
    is_copy INTEGER NOT NULL,        -- 1 = republished copy of another record (hidden in tables)
    {", ".join(f"{n} REAL" for n in KEY_NUTRIENTS)},
    nutrients TEXT NOT NULL,         -- JSON {{nutrient id: value | {{"v","f","m","e"}}}} (see nutrient_json)
    servings TEXT,                   -- JSON [[label_en, label_zh, amount, unit], ...] by amount
    members TEXT NOT NULL,           -- JSON ids of all records of the group (this one included)
    links TEXT,                      -- JSON {{other id: match type}} for direct links inside the group
    similar TEXT,                    -- JSON ids of main records of 'similar' groups
    related TEXT                     -- JSON ids: same source group, nearest energy
) WITHOUT ROWID;
"""
# Only index on D1 (each index costs one extra row write per row): category browsing.
INDEXES = ["CREATE INDEX idx_foods_category ON foods(category, is_primary, source_id)"]
TABLES = ["sources", "nutrients", "categories", "subcategories", "foods"]


def nutrient_json(value, flag, method, estimated):
    """A plain number when there is nothing else to say; else {"v": value, "f": flag, "m": method, "e": 1}."""
    if flag is None and method is None and not estimated:
        return value
    d = {"v": value}
    if flag:
        d["f"] = flag
    if method:
        d["m"] = method
    if estimated:
        d["e"] = 1
    return d


def dumps(x):
    return json.dumps(x, ensure_ascii=False, separators=(",", ":")) if x else None


def build(master=MASTER, out=SERVED):
    src = sqlite3.connect(master)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    db = sqlite3.connect(tmp)
    db.executescript(SCHEMA)
    for i in INDEXES:
        db.execute(i)

    order = {n: i for i, (n,) in enumerate(src.execute("SELECT id FROM nutrients ORDER BY sort_order"))}
    nutr = defaultdict(dict)
    for f, n, v, fl, m, e in src.execute("SELECT food_id, nutrient_id, value, flag, method, estimated FROM food_nutrients"):
        nutr[f][n] = (v, fl, m, e)
    serv = defaultdict(list)
    for f, le, lz, a, u in src.execute("SELECT food_id, label_en, label_zh, amount, unit FROM servings ORDER BY food_id, amount, rowid"):
        serv[f].append([le, lz, a, u])

    foods = [dict(zip(TEXT_COLS, r)) for r in src.execute(f"SELECT {', '.join(TEXT_COLS)} FROM foods")]
    by_id = {f["id"]: f for f in foods}
    clusters = defaultdict(list)
    for f in foods:
        clusters[f["cluster_id"]].append(f)
    for m in clusters.values():
        m.sort(key=lambda f: (f["source_id"], f["id"]))

    kcal = {f["id"]: nutr[f["id"]].get("energy_kcal", (None,))[0] for f in foods}
    links, copies, similar = defaultdict(dict), set(), defaultdict(list)
    for a, b, t in src.execute("SELECT food_id, canonical_id, match_type FROM food_links ORDER BY food_id, canonical_id"):
        ca, cb = by_id[a]["cluster_id"], by_id[b]["cluster_id"]
        if t == "exact_copy":
            copies.add(a)
        if ca == cb:
            links[a].setdefault(b, t)
            links[b].setdefault(a, t)
        elif t == "similar":
            for x, y in ((ca, cb), (cb, ca)):
                if y not in similar[x] and len(similar[x]) < N_SIMILAR:
                    similar[x].append(y)

    # related: main records of the same source and (sub)group, nearest energy first
    groups = defaultdict(list)
    for f in foods:
        if f["is_primary"]:
            groups[(f["source_id"], f["subgroup_en"] or f["group_en"] or "")].append(f["id"])
    sorted_groups = {k: sorted(v, key=lambda i: (kcal[i] or 0, i)) for k, v in groups.items()}
    keys_of = {k: [kcal[i] or 0 for i in v] for k, v in sorted_groups.items()}

    def related(f):
        g = (f["source_id"], f["subgroup_en"] or f["group_en"] or "")
        ids, ks = sorted_groups.get(g, []), keys_of.get(g, [])
        x = kcal[f["id"]] or 0
        lo = hi = bisect.bisect_left(ks, x)
        out = []
        while len(out) < N_RELATED and (lo > 0 or hi < len(ids)):
            if hi < len(ids) and (lo == 0 or abs(ks[hi] - x) <= abs(ks[lo - 1] - x)):
                c, hi = ids[hi], hi + 1
            else:
                lo -= 1
                c = ids[lo]
            if c != f["id"]:
                out.append(c)
        return out

    rows = []
    for f in foods:
        fid, members = f["id"], clusters[f["cluster_id"]]
        n = nutr[fid]
        rows.append([f[c] for c in TEXT_COLS] + [
            len({m["source_id"] for m in members}),
            int(fid in copies),
            *[(n[k][0] if k in n else None) for k in KEY_NUTRIENTS],
            json.dumps({k: nutrient_json(*n[k]) for k in sorted(n, key=order.get)}, ensure_ascii=False, separators=(",", ":")),
            dumps(serv.get(fid)),
            dumps([m["id"] for m in members]),
            dumps(links.get(fid)),
            dumps(similar.get(f["cluster_id"])),
            dumps(related(f)),
        ])
    cols = TEXT_COLS + ["n_sources", "is_copy"] + KEY_NUTRIENTS + ["nutrients", "servings", "members", "links", "similar", "related"]
    db.executemany(f"INSERT INTO foods ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", rows)

    db.executemany("INSERT INTO nutrients VALUES (?, ?, ?, ?, ?, ?)",
                   src.execute("SELECT id, infoods_tag, name_en, name_zh, unit, sort_order FROM nutrients"))
    db.executemany("INSERT INTO sources VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", src.execute(
        "SELECT s.id, s.name, s.publisher, s.country, s.licence, s.attribution, s.url, s.version, s.retrieved_at,"
        " (SELECT COUNT(*) FROM foods f WHERE f.source_id = s.id) FROM sources s"))
    db.executemany("INSERT INTO categories VALUES (?, ?, ?, ?, ?, ?)", src.execute(
        "SELECT c.id, c.name_zh, c.name_en, c.sort_order,"
        " (SELECT COUNT(*) FROM foods f WHERE f.category = c.id AND f.is_primary = 1),"
        " (SELECT COUNT(*) FROM foods f WHERE f.category = c.id) FROM categories c"))
    db.executemany("INSERT INTO subcategories VALUES (?, ?, ?, ?, ?, ?, ?)", src.execute(
        "SELECT s.id, s.category, s.name_zh, s.name_en, s.sort_order,"
        " (SELECT COUNT(*) FROM foods f WHERE f.subcategory = s.id AND f.is_primary = 1),"
        " (SELECT COUNT(*) FROM foods f WHERE f.subcategory = s.id) FROM subcategories s"))
    db.commit()
    db.execute("VACUUM")
    db.close()
    tmp.replace(out)
    print(f"{len(rows)} foods -> {out} ({out.stat().st_size // (1 << 20)} MB)")


if __name__ == "__main__":
    build()
