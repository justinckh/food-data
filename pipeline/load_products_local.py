"""Copy data/export/products.db into the LOCAL D1 database used by `npm run dev` (food-db).

Run from the project root:   python3 -m pipeline.load_products_local      (npm run products:local)

Faster than `wrangler d1 execute --local --file products.sql` (65 MB of SQL). Finds the local
SQLite file of food-db by creating a probe table with wrangler. Does not touch the live D1.
"""
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "export" / "products.db"
STATE = ROOT / ".wrangler" / "state" / "v3" / "d1" / "miniflare-D1DatabaseObject"
TABLES = ["product_categories", "product_markets", "products"]


def local_db_file():
    subprocess.run(["npx", "--yes", "wrangler", "d1", "execute", "food-db", "--local", "--command",
                    "CREATE TABLE IF NOT EXISTS _probe(x)"], cwd=ROOT, check=True, capture_output=True)
    hits = [f for f in STATE.glob("*.sqlite") if f.name != "metadata.sqlite"
            and sqlite3.connect(f).execute("SELECT 1 FROM sqlite_master WHERE name = '_probe'").fetchone()]
    if len(hits) != 1:
        sys.exit(f"Could not find the local food-db file ({len(hits)} candidates)")
    return hits[0]


def main():
    if not SRC.exists():
        sys.exit(f"Missing {SRC}. Run: npm run products")
    db = sqlite3.connect(local_db_file())
    db.execute("DROP TABLE _probe")
    db.execute("ATTACH ? AS src", (str(SRC),))
    for t in ["products_fts", *TABLES]:
        db.execute(f"DROP TABLE IF EXISTS main.{t}")
    for name, sql in db.execute("SELECT name, sql FROM src.sqlite_master WHERE type = 'table' AND name IN (%s)"
                                % ",".join("?" * len(TABLES)), TABLES).fetchall():
        db.execute(sql)
        db.execute(f"INSERT INTO main.{name} SELECT * FROM src.{name}")
    for (sql,) in db.execute("SELECT sql FROM src.sqlite_master WHERE type = 'index' AND sql IS NOT NULL").fetchall():
        db.execute(sql)
    db.execute("CREATE VIRTUAL TABLE products_fts USING fts5(code UNINDEXED, search_text, tokenize='trigram', columnsize=0)")
    db.execute("INSERT INTO products_fts (code, search_text) SELECT code, search_text FROM main.products")
    db.commit()
    print(f"Local D1: {db.execute('SELECT COUNT(*) FROM main.products').fetchone()[0]:,} products loaded.")


if __name__ == "__main__":
    main()
