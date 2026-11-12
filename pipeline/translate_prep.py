"""Prepare machine translation of English-only food names into Hong Kong Chinese.

Run from the project root:   python3 -m pipeline.translate_prep [--pilot N]

One item per food group (cluster) that has no Chinese display name: the English display
name (or the Japanese name for MEXT foods without English). Items that are already in
pipeline/translations_zh.csv are skipped.

Writes data/translate/in/batch-NNN.tsv (BATCH items each; with --pilot N: one mixed
sample file pilot.tsv) and data/translate/RULES.md (the instructions + glossary).
Translators write data/translate/out/<same name>.tsv: key<TAB>translation.
pipeline/translate_merge.py checks the results and adds them to translations_zh.csv.
"""
import csv
import random
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "food.db"
WORK = ROOT / "data" / "translate"
DONE = ROOT / "pipeline" / "translations_zh.csv"
BATCH = 400

RULES = """# Translate food names into Hong Kong Chinese

You translate food names from food composition tables into the words a Hong Kong reader uses.

## Input and output
- Input: a TSV file. Columns: `key`, `english`, `japanese`, `group`, `source`.
  `key` is the text to translate (usually the English name; for some Japanese foods the Japanese name).
  `japanese` (if present) is the original Japanese name: use it to understand the food.
  `group` and `source` are context only.
- Output: a TSV file with exactly 2 columns: `key<TAB>translation`, one line per input line, same order,
  with the header line `key\ttranslation`. Copy `key` exactly, character for character.
- Write the output with a short Python script (csv module, delimiter tab) to avoid quoting mistakes.

## Style
- Traditional Chinese characters, Hong Kong usage (粵語書面常用詞), not Taiwan or Mainland words.
  Use the glossary below. Other common HK words: 薯仔 (potato), 番茄 (tomato), 粟米 (corn), 菠蘿 (pineapple),
  奇異果 (kiwi), 士多啤梨 (strawberry), 車厘子 (cherry), 牛油果 (avocado), 西蘭花 (broccoli), 椰菜花 (cauliflower),
  三文魚 (salmon), 吞拿魚 (tuna), 芝士 (cheese), 忌廉 (cream), 乳酪 (yogurt), 牛油 (butter), 朱古力 (chocolate),
  曲奇 (cookie), 餅乾 (biscuit/cracker), 多士 (toast), 意粉 (spaghetti/pasta), 通粉 (macaroni), 腸仔 (sausage),
  煙肉 (bacon), 火腿 (ham), 雪糕 (ice cream), 汽水 (soft drink), 啤酒 (beer), 豬扒/牛扒 (pork chop/steak),
  免治牛肉 (minced beef), 雞翼 (chicken wing), 雞髀 (chicken drumstick/leg), 雞胸 (chicken breast).
- Format: main food first, then the details in brackets with Chinese commas, e.g.
  "Beef, chuck, blade roast, separable lean only, trimmed to 0\\" fat, choice, cooked, braised"
  -> 牛肩胛肉(只計瘦肉,修脂至0吋,特選級,炆)
  "Chicken, broilers or fryers, wing, meat and skin, cooked, fried, batter" -> 雞翼(連皮,炸漿炸)
- Cooking words: raw 生, cooked 熟, boiled 烚/煮, steamed 蒸, baked 焗, roasted 烤, grilled/broiled 燒烤,
  fried 炸, pan-fried 煎, stir-fried 炒, stewed/braised 炆, microwaved 微波, dried 乾, canned 罐頭,
  frozen 冷凍, smoked 煙燻, salted 鹽醃, drained 已瀝乾, unprepared 未經調製, prepared 已調製.
- Keep useful details (part of the animal, fat level, brand type, "with salt"/"without salt" 有鹽/無鹽,
  "fortified" 強化, "low fat" 低脂). Drop codes and words with no meaning for a reader
  (e.g. "NFS", "USDA Commodity" -> 美國農業部商品; "Includes foods for USDA's Food Distribution Program" -> drop).
- Brand names and product names with no Chinese name: keep the brand in English, translate the food,
  e.g. "KELLOGG'S, CORN FLAKES" -> 粟米片(KELLOGG'S). Fast-food chains: 麥當勞, 肯德基, 漢堡王, 必勝客 etc.
- Species and varieties with no common Chinese name: give the closest common name, not a literal translation.
- No explanations, no notes, no question marks, no alternatives with "/". One name per line.
- If you really cannot tell what the food is, still give the best short name.
- \"commercial\" / \"retail\" (bought from a shop) is NOT translated, like CFS (\"Tart, custard, commercial\" -> 吉士撻).
  Keep 市售 only when another food has the same name without it. \"Composite of trimmed retail cuts\" -> 各部位平均.
- Two different English names must not get the identical translation: keep the detail that makes them different
  (e.g. "meat only" 只計肉 vs "weighed with bones" 連骨稱重, brand, flavour, fat level).

## Glossary (English -> HK word)
"""


def glossary():
    lines = []
    with open(ROOT / "pipeline" / "synonyms.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            hk = (r["hk"] or "").split("|")[0]
            if hk:
                lines.append(f"- {r['en'].replace('|', ' / ')} -> {hk}")
    return "\n".join(lines)


def cfs_examples(db, n=40):
    """CFS's own translations of USDA and Australian names (not the China table: Mainland words)."""
    out = []
    for origin in ("USDA FoodData Central", "Food Standards Australia New Zealand", "CFS Food Research Laboratory"):
        rows = db.execute("SELECT name_en, name_zh FROM foods WHERE source_id = 'cfs' AND origin_source = ? "
                          "AND name_en IS NOT NULL AND name_zh IS NOT NULL ORDER BY id", (origin,)).fetchall()
        random.Random(3).shuffle(rows)
        out += rows[:n]
    return "\n".join(f"- {en} -> {zh}" for en, zh in out)


def items(db):
    done = set()
    if DONE.exists():
        with open(DONE, encoding="utf-8") as f:
            done = {r["key"] for r in csv.DictReader(f)}
    by_key = {}
    for cid, in db.execute("SELECT DISTINCT cluster_id FROM foods WHERE display_zh IS NULL ORDER BY cluster_id"):
        members = db.execute("SELECT source_id, display_en, name_local, group_en, is_primary FROM foods "
                             "WHERE cluster_id = ? ORDER BY is_primary DESC", (cid,)).fetchall()
        src, en, local, group, _ = members[0]
        ja = next((m[2] for m in members if m[0] == "mext"), "")
        key = en or local
        if key in done or key in by_key:
            continue
        by_key[key] = [key, en or "", ja or "", group or "", src]
    return list(by_key.values())


def write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["key", "english", "japanese", "group", "source"])
        w.writerows([[c.replace("\t", " ").replace("\n", " ") for c in r] for r in rows])


def main():
    db = sqlite3.connect(DB)
    rows = items(db)
    (WORK / "RULES.md").parent.mkdir(parents=True, exist_ok=True)
    (WORK / "RULES.md").write_text(RULES + glossary() + "\n\n## Examples of HK style (CFS names)\n"
                                   + cfs_examples(db) + "\n", encoding="utf-8")
    if "--pilot" in sys.argv:
        n = int(sys.argv[sys.argv.index("--pilot") + 1])
        by_src = defaultdict(list)
        for r in rows:
            by_src[r[4]].append(r)
        rnd = random.Random(7)
        pick = []
        for src, rs in sorted(by_src.items()):    # spread over the sources, by their size
            k = max(5, round(n * len(rs) / len(rows)))
            pick += rnd.sample(rs, min(k, len(rs)))
        write(WORK / "in" / "pilot.tsv", pick[:n])
        print(f"{len(pick[:n])} pilot items -> {WORK / 'in' / 'pilot.tsv'}")
        return
    rows.sort(key=lambda r: (r[4], r[3], r[0]))   # same source and group together
    for old in (WORK / "in").glob("batch-*.tsv"):
        old.unlink()
    for i in range(0, len(rows), BATCH):
        write(WORK / "in" / f"batch-{i // BATCH + 1:03d}.tsv", rows[i:i + BATCH])
    print(f"{len(rows)} items -> {(len(rows) + BATCH - 1) // BATCH} batches in {WORK / 'in'}")


if __name__ == "__main__":
    main()
