"""Build data/food.db (the master copy) from scratch.

Run from the project root:   python3 -m pipeline.build_db

The database is always rebuilt in full from source files, never edited by hand.
It is written to a temp file first and only replaces data/food.db on success.
"""
import os
import sqlite3
import sys
from pathlib import Path

from .common import NUTRIENT_IDS, NUTRIENTS
from .importers import afcd, cfs, cnf, cofid, mext, tfda, usda

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "db" / "schema.sql"
OUT = ROOT / "data" / "food.db"

FOOD_COLS = ["id", "source_id", "source_code", "name_en", "name_zh", "name_local", "alias",
             "group_en", "group_zh", "subgroup_en", "subgroup_zh", "description",
             "origin_source", "origin_code", "search_text"]

# Each importer exposes datasets(root) -> (SOURCE dict, rows). Add new sources here.
IMPORTERS = [cfs, tfda, mext, afcd, usda, cofid, cnf]


def import_source(db, src, rows):
    db.execute(
        "INSERT INTO sources (id, name, publisher, country, licence, attribution, url, version, retrieved_at)"
        " VALUES (:id, :name, :publisher, :country, :licence, :attribution, :url, :version, :retrieved_at)", src)
    n_foods = n_values = 0
    for food, nutrients, servings in rows:
        db.execute(
            f"INSERT INTO foods ({', '.join(FOOD_COLS)}) VALUES ({', '.join(':' + c for c in FOOD_COLS)})",
            {c: food.get(c) for c in FOOD_COLS})   # importers may omit optional columns
        for nid, *_ in nutrients:
            if nid not in NUTRIENT_IDS:
                raise SystemExit(f"{src['id']}: unknown nutrient id {nid!r} - add it to pipeline/common.py")
        db.executemany(
            "INSERT INTO food_nutrients (food_id, nutrient_id, value, flag, method, estimated)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [(food["id"], *n[:4], int(n[4]) if len(n) > 4 else 0) for n in nutrients])
        db.executemany(
            "INSERT INTO servings (food_id, label_en, label_zh, amount, unit) VALUES (?, ?, ?, ?, ?)",
            [(food["id"], *s) for s in servings])
        n_foods += 1
        n_values += len(nutrients)
    print(f"  {src['id']:<10} {n_foods:>6} foods  {n_values:>7} values")


def main():
    OUT.parent.mkdir(exist_ok=True)
    tmp = OUT.with_suffix(".db.tmp")
    tmp.unlink(missing_ok=True)
    db = sqlite3.connect(tmp)
    try:
        db.executescript(SCHEMA.read_text("utf-8"))
        db.executemany(
            "INSERT INTO nutrients (id, infoods_tag, name_en, name_zh, unit, sort_order) VALUES (?, ?, ?, ?, ?, ?)",
            [(*n, i) for i, n in enumerate(NUTRIENTS)])
        print("Importing:")
        for mod in IMPORTERS:
            for src, rows in mod.datasets(ROOT):
                import_source(db, src, rows)
        db.execute("INSERT INTO foods_fts(foods_fts) VALUES ('rebuild')")
        bad = db.execute("PRAGMA foreign_key_check").fetchall()
        if bad:
            raise SystemExit(f"foreign key errors: {bad[:5]}")
        db.commit()
        db.execute("VACUUM")
    except BaseException:
        db.close()
        tmp.unlink(missing_ok=True)
        raise
    db.close()
    os.replace(tmp, OUT)
    print(f"-> {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    sys.exit(main())
