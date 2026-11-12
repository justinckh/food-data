"""Incremental upload to Cloudflare D1: send only what changed since the last upload.

The D1 free plan allows 100,000 written rows per day (all databases of the account).
A full load (npm run load:remote) writes ~2.6 million rows, so after the first load
all updates go through this tool.

  python3 -m pipeline.d1_update plan    compare data/food.db with data/export/remote_baseline.db
                                        (= what is on D1 now) and write the changes as SQL
                                        parts of at most MAX_WRITES estimated row writes each
  python3 -m pipeline.d1_update apply   load the next part that is not loaded yet (one per day
                                        on the free plan); after the last part the baseline is
                                        replaced by the new database
  python3 -m pipeline.d1_update status  show the plan and which parts are loaded

State: data/export/update/plan.json, parts in data/export/update/part-N.sql, and the new
database copy that becomes the baseline in data/export/update/pending.db.
Write estimates: 1 per row plus 1 per index on the table (D1 counts index and FTS rows).
"""
import json
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .export_d1 import FTS, INDEXES, TABLES, literal

ROOT = Path(__file__).resolve().parent.parent
CURRENT = ROOT / "data" / "food.db"
BASELINE = ROOT / "data" / "export" / "remote_baseline.db"
DIR = ROOT / "data" / "export" / "update"
PLAN = DIR / "plan.json"
REMOTE_STATE = ROOT / "data" / "export" / "remote_state.json"
MAX_WRITES = 90_000
MAX_STATEMENT = 50_000

KEYS = {"sources": ["id"], "nutrients": ["id"], "categories": ["id"], "foods": ["id"],
        "food_nutrients": ["food_id", "nutrient_id"], "food_links": ["food_id", "canonical_id"],
        "food_concepts": ["food_id", "concept"], "servings": None}   # servings: replaced per food_id


def index_count(table):
    return sum(1 for i in INDEXES if f" ON {table}(" in i)


class Parts:
    def __init__(self):
        self.parts, self.cur, self.cost = [], [], 0

    def add(self, sql, cost, alone=False):
        if self.cur and (self.cost + cost > MAX_WRITES or alone):
            self.close()
        self.cur.append(sql)
        self.cost += cost

    def close(self):
        if self.cur:
            self.parts.append((self.cur, self.cost))
        self.cur, self.cost = [], 0


def batched(head, rows, cost_each, parts):
    batch, size = [], len(head)
    for v in rows:
        if batch and size + len(v) + 1 > MAX_STATEMENT:
            parts.add(head + ",".join(batch) + ";", cost_each * len(batch))
            batch, size = [], len(head)
        batch.append(v)
        size += len(v) + 1
    if batch:
        parts.add(head + ",".join(batch) + ";", cost_each * len(batch))


def plan():
    remote = json.loads(REMOTE_STATE.read_text()) if REMOTE_STATE.exists() else {"indexes": [], "fts": False}
    DIR.mkdir(parents=True, exist_ok=True)
    pending = DIR / "pending.db"
    shutil.copy(CURRENT, pending)
    db = sqlite3.connect(pending)
    db.execute(f"ATTACH DATABASE '{BASELINE}' AS old")
    parts, summary = Parts(), {}

    for t in TABLES:
        cols = [r[1] for r in db.execute(f"PRAGMA main.table_info({t})")]
        old_cols = [r[1] for r in db.execute(f"PRAGMA old.table_info({t})")]
        n_idx = index_count(t)
        if not old_cols:                                   # new table: create and fill
            ddl = db.execute("SELECT sql FROM main.sqlite_master WHERE type='table' AND name=?", (t,)).fetchone()[0]
            ddl = "\n".join(l for l in ddl.splitlines() if "REFERENCES" not in l or "NOT NULL" in l)
            parts.add(ddl.replace(" REFERENCES foods(id) ON DELETE CASCADE", "") + ";", 1)
            rows = db.execute(f"SELECT {', '.join(cols)} FROM main.{t}").fetchall()
            batched(f"INSERT INTO {t} ({', '.join(cols)}) VALUES ",
                    ["(" + ",".join(literal(x) for x in r) + ")" for r in rows], 1 + n_idx, parts)
            summary[t] = f"new table, {len(rows)} rows"
            continue
        for c in cols:                                     # new columns
            if c not in old_cols:
                info = next(r for r in db.execute(f"PRAGMA main.table_info({t})") if r[1] == c)
                default = f" DEFAULT {info[4]}" if info[4] is not None else ""
                notnull = " NOT NULL" if info[3] and default else ""
                parts.add(f"ALTER TABLE {t} ADD COLUMN {c} {info[2]}{notnull}{default};", 1)

        common = [c for c in cols if c in old_cols]
        key = KEYS[t]
        if key is None:                                    # servings: compare per food
            new = {}
            for r in db.execute(f"SELECT food_id, {', '.join(cols)} FROM main.{t}"):
                new.setdefault(r[0], []).append(r[1:])
            old = {}
            for r in db.execute(f"SELECT food_id, {', '.join(common)} FROM old.{t}"):
                old.setdefault(r[0], []).append(r[1:])
            changed = [f for f in set(new) | set(old) if sorted(map(repr, new.get(f, []))) != sorted(map(repr, old.get(f, [])))]
            for i in range(0, len(changed), 200):
                ids = ",".join(literal(f) for f in changed[i:i + 200])
                parts.add(f"DELETE FROM {t} WHERE food_id IN ({ids});", (1 + n_idx) * len(changed[i:i + 200]))
            rows = [r for f in changed for r in new.get(f, [])]
            batched(f"INSERT INTO {t} ({', '.join(cols)}) VALUES ",
                    ["(" + ",".join(literal(x) for x in r) + ")" for r in rows], 1 + n_idx, parts)
            summary[t] = f"{len(changed)} foods changed"
            continue

        kcols = ", ".join(key)
        new = {r[:len(key)]: r[len(key):] for r in db.execute(f"SELECT {kcols}, {', '.join(cols)} FROM main.{t}")}
        old = {r[:len(key)]: r[len(key):] for r in db.execute(f"SELECT {kcols}, {', '.join(common)} FROM old.{t}")}
        added = [k for k in new if k not in old]
        removed = [k for k in old if k not in new]
        pos = {c: i for i, c in enumerate(cols)}
        opos = {c: i for i, c in enumerate(common)}
        changed = [k for k in new if k in old and
                   (any(new[k][pos[c]] != old[k][opos[c]] for c in common) or
                    any(new[k][pos[c]] is not None for c in cols if c not in old_cols))]

        def where(k):
            return " AND ".join(f"{c} = {literal(v)}" for c, v in zip(key, k))

        for k in removed:
            parts.add(f"DELETE FROM {t} WHERE {where(k)};", 1 + n_idx)
        if t == "foods":
            # UPDATE only the changed columns (cheaper than replacing the row)
            for k in changed:
                sets = [f"{c} = {literal(new[k][pos[c]])}" for c in cols
                        if c not in key and (c not in opos or new[k][pos[c]] != old[k][opos[c]])]
                parts.add(f"UPDATE foods SET {', '.join(sets)} WHERE {where(k)};", 2)
        else:
            batched(f"INSERT OR REPLACE INTO {t} ({', '.join(cols)}) VALUES ",
                    ["(" + ",".join(literal(x) for x in new[k]) + ")" for k in changed], 2 * (1 + n_idx), parts)
        batched(f"INSERT INTO {t} ({', '.join(cols)}) VALUES ",
                ["(" + ",".join(literal(x) for x in new[k]) + ")" for k in added], 1 + n_idx, parts)
        summary[t] = f"{len(added)} new, {len(changed)} changed, {len(removed)} removed"

    # indexes that D1 does not have yet
    new_indexes = [i for i in INDEXES if i.split()[2] not in remote["indexes"]]
    for i in new_indexes:
        table = i.split(" ON ")[1].split("(")[0]
        n = db.execute(f"SELECT COUNT(*) FROM main.{table}").fetchone()[0]
        parts.add(i.replace("CREATE INDEX", "CREATE INDEX IF NOT EXISTS") + ";", n, alone=n > MAX_WRITES // 2)
    summary["indexes"] = [i.split()[2] for i in new_indexes]

    # search index
    if not remote["fts"]:
        n = db.execute("SELECT COUNT(*) FROM main.foods").fetchone()[0]
        parts.add(FTS, n + 1, alone=True)
        summary["search_fts"] = f"create, {n} rows"
    else:
        ids = [r[0] for r in db.execute(
            "SELECT id FROM main.foods f WHERE NOT EXISTS (SELECT 1 FROM old.foods o WHERE o.id = f.id "
            "AND o.search_text = f.search_text)")]
        gone = [r[0] for r in db.execute("SELECT id FROM old.foods WHERE id NOT IN (SELECT id FROM main.foods)")]
        for i in range(0, len(ids + gone), 200):
            chunk = ",".join(literal(x) for x in (ids + gone)[i:i + 200])
            parts.add(f"DELETE FROM search_fts WHERE food_id IN ({chunk});", len((ids + gone)[i:i + 200]))
        for i in range(0, len(ids), 200):
            chunk = ",".join(literal(x) for x in ids[i:i + 200])
            parts.add(f"INSERT INTO search_fts (text, food_id) SELECT search_text, id FROM foods WHERE id IN ({chunk});",
                      len(ids[i:i + 200]))
        summary["search_fts"] = f"{len(ids)} updated, {len(gone)} removed"
    parts.close()

    for old_part in DIR.glob("part-*.sql"):
        old_part.unlink()
    files = []
    for n, (stmts, cost) in enumerate(parts.parts, 1):
        f = DIR / f"part-{n}.sql"
        f.write_text("\n".join(stmts) + "\n", encoding="utf-8")
        files.append({"file": f.name, "estimated_writes": cost, "loaded": None})
    state = {"created": datetime.now(timezone.utc).isoformat(timespec="seconds"), "summary": summary,
             "parts": files, "remote_after": {"indexes": [i.split()[2] for i in INDEXES], "fts": True}}
    PLAN.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    status()


def status():
    if not PLAN.exists():
        print("no plan - run: python3 -m pipeline.d1_update plan")
        return
    state = json.loads(PLAN.read_text())
    print(f"plan of {state['created']}:")
    for t, s in state["summary"].items():
        print(f"  {t:<15} {s}")
    for p in state["parts"]:
        print(f"  {p['file']:<12} ~{p['estimated_writes']:>7,} writes   {'loaded ' + p['loaded'] if p['loaded'] else 'NOT loaded'}")


def apply():
    state = json.loads(PLAN.read_text())
    todo = [p for p in state["parts"] if not p["loaded"]]
    if not todo:
        print("all parts are loaded")
        return
    p = todo[0]
    print(f"loading {p['file']} (~{p['estimated_writes']:,} writes) ...", flush=True)
    r = subprocess.run(["npx", "--yes", "wrangler", "d1", "execute", "food-data", "--remote",
                        "--file", str(DIR / p["file"]), "--yes"], cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-2000:], r.stderr[-2000:], sep="\n")
        sys.exit(f"{p['file']} failed - nothing marked as loaded. On the free plan, wait for midnight UTC.")
    p["loaded"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    PLAN.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    if all(x["loaded"] for x in state["parts"]):
        shutil.copy(DIR / "pending.db", BASELINE)
        REMOTE_STATE.write_text(json.dumps(state["remote_after"], indent=2))
        print("all parts loaded: baseline updated. Change DATA_VERSION / API_VERSION and deploy.")
    status()


if __name__ == "__main__":
    {"plan": plan, "apply": apply, "status": status}[sys.argv[1] if len(sys.argv) > 1 else "status"]()
