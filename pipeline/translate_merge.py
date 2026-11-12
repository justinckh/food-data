"""Check machine translations and add them to pipeline/translations_zh.csv.

Run from the project root:   python3 -m pipeline.translate_merge [name ...]
  (names: e.g. pilot batch-001; default: every file in data/translate/out/)

Checks per file (a file with an error is not added; redo it):
  - same keys in the same order as data/translate/in/<name>.tsv
  - every translation has Chinese characters, no tab/newline, no "?", no "/" between Chinese words
Warnings (shown, the file is still added):
  - a glossary word in the English name, but no character of the HK word in the translation
  - Mainland or Taiwan words where HK uses another word (土豆, 西紅柿, 玉米, 鳳梨, 酪梨, ...)
translations_zh.csv columns: key, zh, file. The build (pipeline/display.py) uses it for food
groups that have no Chinese name, and marks those names as machine translations (foods.zh_mt).
"""
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "data" / "translate"
DONE = ROOT / "pipeline" / "translations_zh.csv"
HAN = re.compile(r"[一-鿿]")
ALT = re.compile(r"[\u4e00-\u9fff]\s*[/／]\s*[\u4e00-\u9fff]")
NOT_HK = {"土豆": "薯仔", "马铃薯": "薯仔", "馬鈴薯": "薯仔", "西紅柿": "番茄", "玉米": "粟米", "鳳梨": "菠蘿",
          "酪梨": "牛油果", "鱷梨": "牛油果", "起司": "芝士", "奶酪": "芝士", "鮮奶油": "忌廉", "優格": "乳酪",
          "酸奶": "乳酪", "巧克力": "朱古力", "鮭魚": "三文魚", "鮪魚": "吞拿魚", "義大利麵": "意粉",
          "培根": "煙肉", "冰淇淋": "雪糕", "花椰菜": "西蘭花/椰菜花", "綠花椰菜": "西蘭花", "草莓": "士多啤梨",
          "櫻桃": "車厘子", "奇異果": None, "高麗菜": "椰菜", "番薯": None, "地瓜": "番薯", "洋芋": "薯仔"}
NOT_HK = {k: v for k, v in NOT_HK.items() if v}


def read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def glossary():
    out = []
    with open(ROOT / "pipeline" / "synonyms.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            hk = [w for w in (r["hk"] or "").split("|") if w]
            if hk:
                for en in r["en"].split("|"):
                    out.append((re.compile(rf"\b{re.escape(en)}\b", re.I), hk))
    return out


def main():
    names = sys.argv[1:] or sorted(p.stem for p in (WORK / "out").glob("*.tsv"))
    done = {r["key"]: r for r in read(DONE)} if DONE.exists() else {}
    gl = glossary()
    added = 0
    for name in names:
        src, out = WORK / "in" / f"{name}.tsv", WORK / "out" / f"{name}.tsv"
        if not out.exists():
            print(f"{name}: no output yet")
            continue
        inp, res = read(src), read(out)
        errors, warnings = [], []
        if [r["key"] for r in inp] != [r.get("key") for r in res]:
            errors.append(f"keys differ from the input ({len(inp)} in, {len(res)} out)")
        for r in res:
            zh = (r.get("translation") or "").strip()
            # "/" is an error only between Chinese words (alternatives such as 低脂/脫脂); 1/8吋 is fine
            if not HAN.search(zh) or "?" in zh or "？" in zh or ALT.search(zh) or "\t" in zh or "\n" in zh:
                errors.append(f"bad translation: {r.get('key')!r} -> {zh!r}")
                continue
            for pat, hk in gl:
                # warn only when no character of the HK word is used (牛柳 for "beef" is fine)
                if pat.search(r["key"]) and not any(ch in zh for w in hk for ch in w):
                    warnings.append(f"glossary {hk[0]}: {r['key']} -> {zh}")
                    break
            for bad, good in NOT_HK.items():
                if bad in zh and not any(g in zh for g in good.split("/")):
                    warnings.append(f"not HK word {bad} (use {good}): {r['key']} -> {zh}")
        print(f"{name}: {len(res)} lines, {len(errors)} errors, {len(warnings)} warnings")
        for m in (errors + warnings)[:40]:
            print("   ", m)
        if errors:
            print(f"    {name} NOT added - redo it")
            continue
        for r in res:
            done[r["key"]] = {"key": r["key"], "zh": r["translation"].strip(), "file": name}
            added += 1
    with open(DONE, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["key", "zh", "file"], lineterminator="\n")
        w.writeheader()
        w.writerows(sorted(done.values(), key=lambda r: r["key"]))
    print(f"{added} added; {len(done)} translations in {DONE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
