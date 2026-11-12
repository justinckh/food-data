"""Export the served database (pipeline/serve_db.py) as one SQL file for Cloudflare D1:
data/export/d1.sql

Run from the project root:   python3 -m pipeline.export_d1
The file drops and re-creates every table, so a load always replaces all data. A full
load writes ~85k rows (the D1 free plan allows 100k rows a day); use it for
the LOCAL dev database; the live database is updated with pipeline/d1_update.py.
    npx wrangler d1 execute food-db --local --file data/export/d1.sql   (local test)

- search_fts (FTS5, trigram) is built inside D1 from foods.search_text, so the search
  reads only matching rows for queries of 3+ characters.
- No BEGIN/COMMIT: D1 imports run without explicit transactions.
"""
import sqlite3

from .serve_db import INDEXES, SERVED, TABLES, build

OUT = SERVED.parent / "d1.sql"
D1_DATABASE = "food-db"     # database_name in wrangler.jsonc
# Trigram search index for queries of 3+ characters (functions/api/search.js)
# columnsize=0: no per-row size table (only needed for bm25 ranking, which the site does not use);
# this halves the rows the search index writes (~1.1 per food instead of ~2.1).
FTS = ("CREATE VIRTUAL TABLE search_fts USING fts5(text, food_id UNINDEXED, tokenize='trigram', columnsize=0);\n"
       "INSERT INTO search_fts (text, food_id) SELECT search_text, id FROM foods;")
MAX_STATEMENT = 50_000   # characters per INSERT; D1 rejects statements over 100 KB


def literal(v):
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return repr(v)
    return "'" + str(v).replace("'", "''") + "'"


def table_ddl(db, t):
    return db.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (t,)).fetchone()[0]


def main():
    build()
    src = sqlite3.connect(SERVED)
    total = 0
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("DROP TABLE IF EXISTS search_fts;\n")
        for t in reversed(TABLES):
            f.write(f"DROP TABLE IF EXISTS {t};\n")
        for t in TABLES:
            f.write(table_ddl(src, t) + ";\n")
            cols = [r[1] for r in src.execute(f"PRAGMA table_info({t})")]
            head = f"INSERT INTO {t} ({', '.join(cols)}) VALUES "
            batch, size = [], len(head)
            for r in src.execute(f"SELECT {', '.join(cols)} FROM {t}"):
                v = "(" + ",".join(literal(x) for x in r) + ")"
                if batch and size + len(v) + 1 > MAX_STATEMENT:
                    f.write(head + ",".join(batch) + ";\n")
                    batch, size = [], len(head)
                batch.append(v)
                size += len(v) + 1
                total += 1
            if batch:
                f.write(head + ",".join(batch) + ";\n")
        for i in INDEXES:
            f.write(i + ";\n")
        f.write(FTS + "\n")
    print(f"{total} rows -> {OUT} ({OUT.stat().st_size // (1 << 20)} MB)")


if __name__ == "__main__":
    main()
