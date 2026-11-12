"""Incremental upload to Cloudflare D1: send only what changed since the last upload.

The D1 free plan allows 100,000 written rows per day (all databases of the account).
The served database (pipeline/serve_db.py) has one row per food, so a full upload is
~26k food rows + index + search index; a normal update is much smaller.

  python3 -m pipeline.d1_update plan    build data/export/served.db, compare it with the copy
                                        of what is on D1 now (baseline) and write the changes
                                        as SQL parts of at most MAX_WRITES estimated writes each
  python3 -m pipeline.d1_update apply   load the next part that is not loaded yet (one per day
                                        on the free plan if the parts are large); after the last
                                        part the baseline is replaced by the new database
  python3 -m pipeline.d1_update status  show the plan and which parts are loaded

State per D1 database: data/export/remote/<database>/baseline.db and state.json
(no baseline = empty database). Plan: data/export/update/plan.json, part-N.sql, pending.db.
Write estimates: 1 per row plus 1 per index on the table; search index: 1.1 per food.
"""
import json
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .export_d1 import D1_DATABASE, FTS, literal, table_ddl
from .serve_db import INDEXES, SERVED, TABLES, build

ROOT = Path(__file__).resolve().parent.parent
REMOTE = ROOT / "data" / "export" / "remote" / D1_DATABASE
BASELINE = REMOTE / "baseline.db"
REMOTE_STATE = REMOTE / "state.json"
DIR = ROOT / "data" / "export" / "update"
PLAN = DIR / "plan.json"
MAX_WRITES = 90_000
MAX_STATEMENT = 50_000
FTS_COST = 1.1   # FTS5 (columnsize=0) writes a content row per document + index blocks (~1 per 13 docs)


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
    build()
    remote = json.loads(REMOTE_STATE.read_text()) if REMOTE_STATE.exists() else {"indexes": [], "fts": False}
    DIR.mkdir(parents=True, exist_ok=True)
    pending = DIR / "pending.db"
    shutil.copy(SERVED, pending)
    db = sqlite3.connect(pending)
    db.execute(f"ATTACH DATABASE '{BASELINE if BASELINE.exists() else ':memory:'}' AS old")
    parts, summary = Parts(), {}
    fts_ids, fts_gone = [], []

    for t in TABLES:
        cols = [r[1] for r in db.execute(f"PRAGMA main.table_info({t})")]
        old_cols = [r[1] for r in db.execute(f"PRAGMA old.table_info({t})")]
        n_idx = index_count(t)
        if not old_cols:                                   # new table: create and fill
            parts.add(table_ddl(db, t) + ";", 1)
            rows = db.execute(f"SELECT {', '.join(cols)} FROM main.{t}").fetchall()
            # indexes are created after the rows (counted below), so each insert is 1 write
            batched(f"INSERT INTO {t} ({', '.join(cols)}) VALUES ",
                    ["(" + ",".join(literal(x) for x in r) + ")" for r in rows], 1, parts)
            summary[t] = f"new table, {len(rows)} rows"
            continue
        if cols != old_cols:
            sys.exit(f"{t}: columns changed ({old_cols} -> {cols}). Add a migration step here first.")

        new = {r[0]: r for r in db.execute(f"SELECT {', '.join(cols)} FROM main.{t}")}
        old = {r[0]: r for r in db.execute(f"SELECT {', '.join(cols)} FROM old.{t}")}
        added = [k for k in new if k not in old]
        removed = [k for k in old if k not in new]
        changed = [k for k in new if k in old and new[k] != old[k]]

        for i in range(0, len(removed), 200):
            ids = removed[i:i + 200]
            parts.add(f"DELETE FROM {t} WHERE id IN ({','.join(map(literal, ids))});", (1 + n_idx) * len(ids))
        # UPDATE only the changed columns (an UPDATE of unindexed columns is 1 write)
        for k in changed:
            sets = [f"{c} = {literal(v)}" for c, v, o in zip(cols, new[k], old[k]) if v != o]
            touched = {c for c, v, o in zip(cols, new[k], old[k]) if v != o}
            idx_cols = {"category", "is_primary", "source_id"} if t == "foods" else set()
            parts.add(f"UPDATE {t} SET {', '.join(sets)} WHERE id = {literal(k)};", 1 + (n_idx if touched & idx_cols else 0))
        batched(f"INSERT INTO {t} ({', '.join(cols)}) VALUES ",
                ["(" + ",".join(literal(x) for x in new[k]) + ")" for k in added], 1 + n_idx, parts)
        summary[t] = f"{len(added)} new, {len(changed)} changed, {len(removed)} removed"
        if t == "foods":
            s = cols.index("search_text")
            fts_ids = added + [k for k in changed if new[k][s] != old[k][s]]
            fts_gone = removed + [k for k in changed if new[k][s] != old[k][s]]

    new_indexes = [i for i in INDEXES if i.split()[2] not in remote["indexes"]]
    for i in new_indexes:
        table = i.split(" ON ")[1].split("(")[0]
        n = db.execute(f"SELECT COUNT(*) FROM main.{table}").fetchone()[0]
        parts.add(i.replace("CREATE INDEX", "CREATE INDEX IF NOT EXISTS") + ";", n)
    summary["indexes"] = [i.split()[2] for i in new_indexes] or "none new"

    if not remote["fts"]:
        n = db.execute("SELECT COUNT(*) FROM main.foods").fetchone()[0]
        parts.add(FTS, round(FTS_COST * n), alone=parts.cost + FTS_COST * n > MAX_WRITES)
        summary["search_fts"] = f"create, {n} rows"
    else:
        for i in range(0, len(fts_gone), 200):
            chunk = fts_gone[i:i + 200]
            parts.add(f"DELETE FROM search_fts WHERE food_id IN ({','.join(map(literal, chunk))});", round(FTS_COST * len(chunk)))
        for i in range(0, len(fts_ids), 200):
            chunk = fts_ids[i:i + 200]
            parts.add(f"INSERT INTO search_fts (text, food_id) SELECT search_text, id FROM foods "
                      f"WHERE id IN ({','.join(map(literal, chunk))});", round(FTS_COST * len(chunk)))
        summary["search_fts"] = f"{len(fts_ids)} updated"
    parts.close()

    for old_part in DIR.glob("part-*.sql"):
        old_part.unlink()
    files = []
    for n, (stmts, cost) in enumerate(parts.parts, 1):
        f = DIR / f"part-{n}.sql"
        f.write_text("\n".join(stmts) + "\n", encoding="utf-8")
        files.append({"file": f.name, "estimated_writes": cost, "loaded": None})
    state = {"created": datetime.now(timezone.utc).isoformat(timespec="seconds"), "database": D1_DATABASE,
             "summary": summary, "parts": files,
             "remote_after": {"indexes": [i.split()[2] for i in INDEXES], "fts": True}}
    PLAN.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    status()


def status():
    if not PLAN.exists():
        print("no plan - run: python3 -m pipeline.d1_update plan")
        return
    state = json.loads(PLAN.read_text())
    print(f"plan of {state['created']} for D1 database {state['database']}:")
    for t, s in state["summary"].items():
        print(f"  {t:<15} {s}")
    if not state["parts"]:
        print("  nothing to upload")
    for p in state["parts"]:
        print(f"  {p['file']:<12} ~{p['estimated_writes']:>7,} writes   {'loaded ' + p['loaded'] if p['loaded'] else 'NOT loaded'}")


def apply(target="--remote"):
    state = json.loads(PLAN.read_text())
    todo = [p for p in state["parts"] if not p["loaded"]]
    if not todo:
        print("all parts are loaded")
        return
    p = todo[0]
    print(f"loading {p['file']} (~{p['estimated_writes']:,} writes) into {state['database']} ...", flush=True)
    r = subprocess.run(["npx", "--yes", "wrangler", "d1", "execute", state["database"], target,
                        "--file", str(DIR / p["file"]), "--yes"], cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-2000:], r.stderr[-2000:], sep="\n")
        sys.exit(f"{p['file']} failed - nothing marked as loaded. On the free plan, wait for midnight UTC.")
    print(r.stdout[-600:])
    p["loaded"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    PLAN.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    if all(x["loaded"] for x in state["parts"]):
        REMOTE.mkdir(parents=True, exist_ok=True)
        shutil.copy(DIR / "pending.db", BASELINE)
        REMOTE_STATE.write_text(json.dumps(state["remote_after"], indent=2))
        print("all parts loaded: baseline updated. Change DATA_VERSION / API_VERSION and deploy.")
    status()


if __name__ == "__main__":
    {"plan": plan, "apply": apply, "status": status}[sys.argv[1] if len(sys.argv) > 1 else "status"]()
