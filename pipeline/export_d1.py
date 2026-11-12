"""Export data/food.db as a SQL file for Cloudflare D1: data/export/d1.sql

Run from the project root:   python3 -m pipeline.export_d1
Then load it (see PROJECT.md 4.4):
    npx wrangler d1 execute food-data --local  --file data/export/d1.sql   (local test)
    npx wrangler d1 execute food-data --remote --file data/export/d1.sql   (live)

- The file drops and re-creates every table, so a load always replaces all data.
- No FTS virtual table: the API searches foods.search_text with LIKE (26k rows, fast),
  which avoids D1 export/import limits on virtual tables.
- No BEGIN/COMMIT: D1 imports run without explicit transactions.
"""
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "food.db"
OUT = ROOT / "data" / "export" / "d1.sql"

TABLES = ["sources", "nutrients", "foods", "food_nutrients", "servings", "food_links", "food_concepts"]
INDEXES = [
    "CREATE INDEX idx_foods_cluster ON foods(cluster_id)",
    "CREATE INDEX idx_foods_primary ON foods(is_primary, source_id)",
    "CREATE INDEX idx_foods_group ON foods(source_id, group_en, subgroup_en)",
    "CREATE INDEX idx_fn_nutrient_value ON food_nutrients(nutrient_id, value)",
    "CREATE INDEX idx_servings_food ON servings(food_id)",
    "CREATE INDEX idx_links_food ON food_links(food_id)",
    "CREATE INDEX idx_links_canonical ON food_links(canonical_id)",
    "CREATE INDEX idx_concepts ON food_concepts(concept)",
]
MAX_STATEMENT = 50_000   # characters per INSERT; D1 rejects statements over 100 KB


def literal(v):
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return repr(v)
    return "'" + str(v).replace("'", "''") + "'"


def main():
    src = sqlite3.connect(DB)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with open(OUT, "w", encoding="utf-8") as f:
        for t in reversed(TABLES):
            f.write(f"DROP TABLE IF EXISTS {t};\n")
        for t in TABLES:
            ddl = src.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (t,)).fetchone()[0]
            # foreign keys are checked at build time; D1 loads tables in bulk without them
            ddl = "\n".join(line for line in ddl.splitlines() if "REFERENCES" not in line or "NOT NULL" in line)
            ddl = ddl.replace(" REFERENCES foods(id) ON DELETE CASCADE", "").replace(" REFERENCES sources(id)", "") \
                     .replace(" REFERENCES nutrients(id)", "")
            f.write(ddl + ";\n")
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
    print(f"{total} rows -> {OUT.relative_to(ROOT)} ({OUT.stat().st_size // (1 << 20)} MB)")


if __name__ == "__main__":
    main()
