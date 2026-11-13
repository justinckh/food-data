"""Download the live database from Cloudflare D1 (for collaborators).

Run from the project root:   python3 -m pipeline.d1_download [--local] [--no-baseline]
                             (npm run pull, npm run pull:local)

Needs: Node.js, a wrangler login (npx wrangler login) with access to the Cloudflare account in
.env (CLOUDFLARE_ACCOUNT_ID). Reads ~27,000 rows from D1 (the free plan allows 5 million a day).

What it does:
  1. Exports the served tables (sources, nutrients, categories, subcategories, foods) of the D1
     database in wrangler.jsonc to data/export/download/dump.sql (wrangler d1 export --remote).
  2. Makes the SQLite file data/export/download/remote.db from it and checks the row counts.
  3. Unless --no-baseline: makes it the update baseline (data/export/remote/<database>/), so
     `npm run update:plan` on this computer sends only the changes from the live data.
     An unfinished update plan is removed (it was made against another baseline).
  4. With --local: loads it into the local D1 database used by `npm run dev`, with the search
     index, so the site runs on this computer with the live data.

The master database data/food.db cannot be downloaded: D1 has only the served layout. To change
the data itself, build data/food.db from the raw files (PROJECT.md 2.3, npm run build).
"""
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

from .export_d1 import D1_DATABASE, FTS
from .serve_db import INDEXES, TABLES

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "data" / "export" / "download"
DUMP = DIR / "dump.sql"
DB = DIR / "remote.db"
REMOTE = ROOT / "data" / "export" / "remote" / D1_DATABASE
UPDATE = ROOT / "data" / "export" / "update"


def wrangler(*args):
    r = subprocess.run(["npx", "--yes", "wrangler", *args], cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-2000:], r.stderr[-2000:], sep="\n")
        sys.exit(f"wrangler {args[0]} {args[1]} failed (logged in? npx wrangler login; account in .env)")
    return r.stdout


def remote_state():
    """Indexes and search index on D1 (the table export does not include them)."""
    out = wrangler("d1", "execute", D1_DATABASE, "--remote", "--json", "--command",
                   "SELECT type, name FROM sqlite_master WHERE (type = 'index' AND name LIKE 'idx_%') OR name = 'search_fts'")
    rows = json.loads(out)[0]["results"]
    return {"indexes": [r["name"] for r in rows if r["type"] == "index"], "fts": any(r["name"] == "search_fts" for r in rows)}


def download():
    DIR.mkdir(parents=True, exist_ok=True)
    print(f"exporting {D1_DATABASE} (remote) ...", flush=True)
    tables = [a for t in TABLES for a in ("--table", t)]
    wrangler("d1", "export", D1_DATABASE, "--remote", *tables, "--output", str(DUMP), "-y")
    tmp = DB.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    db = sqlite3.connect(tmp)
    db.executescript(DUMP.read_text(encoding="utf-8"))
    counts = {t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}
    db.close()
    tmp.replace(DB)
    print("  " + ", ".join(f"{t} {n:,}" for t, n in counts.items()))
    if counts["foods"] == 0:
        sys.exit("the remote database has no foods - nothing was changed")


def set_baseline():
    REMOTE.mkdir(parents=True, exist_ok=True)
    shutil.copy(DB, REMOTE / "baseline.db")
    (REMOTE / "state.json").write_text(json.dumps(remote_state(), indent=2))
    plan = UPDATE / "plan.json"
    if plan.exists() and any(not p["loaded"] for p in json.loads(plan.read_text())["parts"]):
        shutil.rmtree(UPDATE)
        print("  an unfinished update plan was removed (made against an older baseline)")
    print(f"  baseline set: {REMOTE.relative_to(ROOT)}")


def load_local():
    sql = DIR / "local.sql"
    with open(sql, "w", encoding="utf-8") as f:
        f.write("DROP TABLE IF EXISTS search_fts;\n")
        for t in reversed(TABLES):
            f.write(f"DROP TABLE IF EXISTS {t};\n")
        f.write(DUMP.read_text(encoding="utf-8").replace("PRAGMA defer_foreign_keys=TRUE;\n", ""))
        for i in INDEXES:
            f.write(i.replace("CREATE INDEX", "CREATE INDEX IF NOT EXISTS") + ";\n")
        f.write(FTS + "\n")
    print("loading into the local D1 database ...", flush=True)
    wrangler("d1", "execute", D1_DATABASE, "--local", "--file", str(sql), "--yes")
    print("  done: npm run dev")


def main():
    download()
    if "--no-baseline" not in sys.argv:
        set_baseline()
    if "--local" in sys.argv:
        load_local()
    print(f"downloaded: {DB.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
