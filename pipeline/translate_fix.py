"""Clean-up rules for machine translations (pipeline/translations_zh.csv), agreed with the user.

Run from the project root:   python3 -m pipeline.translate_fix
Safe to run again (each rule gives the same result the second time).
  1. Brand names: ALL-CAPS words -> normal case (HERSHEY'S -> Hershey's); brand parts inside the
     brackets move to the front: 糖果(HERSHEY'S,ALMOND JOY BITES) -> Hershey's Almond Joy Bites 糖果.
     Maker names before a brand are dropped (ABBOTT NUTRITION, SIMILAC -> Similac).
  2. "ready-to-feed" infant formula: 即飲 -> 即飲裝.
  3. Indigenous foods (Canada CNF "Indigenous", USDA "Alaska Native"): 原住民 -> 北美原住民傳統食物.
  4. fortified / enriched: 無強化, 未強化, 非強化 -> 無添加營養素; a lone 強化 -> 添加營養素.
"""
import csv
import re
from pathlib import Path

P = Path(__file__).resolve().parent / "translations_zh.csv"
HAN = re.compile(r"[぀-ヿ一-鿿]")
ACRONYMS = {"DHA", "ARA", "EPA", "KFC", "USDA", "BBQ", "MCT", "TGI", "IHOP", "UHT", "II", "III", "XL", "NFS", "DIY", "LGG", "GOS", "FOS", "HMO", "LCP", "RTF", "PM", "AR", "HA"}
SPECIAL = {"MCDONALD'S": "McDonald's", "MCDONALDS": "McDonald's", "DIGIORNO": "DiGiorno", "OREO": "Oreo",
           "M&M'S": "M&M's", "REESE'S": "Reese's", "KELLOGG'S": "Kellogg's", "T.G.I.": "T.G.I."}
MAKERS = {"Abbott Nutrition", "Abbott", "Mead Johnson", "PBM Products", "Perrigo", "Nestle", "Nestlé"}


SMALL = {"WITH", "AND", "OF", "THE", "IN", "FOR", "OR"}


def case(word, first=True):
    if not first and word.upper() in SMALL:
        return word.lower()
    if word.upper() in SPECIAL:
        return SPECIAL[word.upper()]
    letters = re.sub(r"[^A-Za-z]", "", word)
    if len(letters) < 3 or not letters.isupper() or letters in ACRONYMS:
        return word
    return "-".join(p[:1] + p[1:].lower() for p in word.split("-"))


def fix_case(text):
    def one(m):
        before = text[:m.start()].rstrip()
        return case(m.group(0), first=not before or not re.search(r"[A-Za-z]$", before))
    return re.sub(r"[A-Za-z][A-Za-z'&\.\-]*", one, text)


def space(z):
    """A space between a brand (3+ letters, not an acronym) and the Chinese name after it."""
    def one(m):
        word = m.group(1)
        letters = re.sub(r"[^A-Za-z]", "", word.split()[-1])
        return m.group(0) if len(letters) < 3 or letters.upper() in ACRONYMS else f"{word} {m.group(2)}"
    return re.sub(r"([A-Za-z][A-Za-z'\.&\-]*)([\u4e00-\u9fff])", one, z)


def brands_first(zh):
    m = re.match(r"^([^()]*)\(([^()]*)\)(.*)$", zh)
    if not m:
        return zh
    head, inner, tail = m.groups()
    parts = [p.strip() for p in inner.split(",")]
    latin = [p for p in parts if p and not HAN.search(p) and re.search(r"[A-Za-z]", p)]
    if not latin or not HAN.search(head):
        return zh
    rest = [p for p in parts if p not in latin]
    names = [p for p in latin if p not in MAKERS] or latin
    out = " ".join(names) + " " + head.strip()
    return out + (f"({','.join(rest)})" if rest else "") + tail


def fix(key, zh):
    k = key.lower()
    z = fix_case(zh)
    z = brands_first(z)
    z = space(z)                                                          # "Ocean Spray白小紅莓" -> space
    if "formula" in k and re.search(r"ready[- ]to[- ]feed", k):
        z = re.sub(r"即飲(?!裝)", "即飲裝", z)
    if "indigenous" in k or "alaska native" in k or "american indian" in k:
        z = re.sub(r"(北美)?(阿拉斯加)?原住民(傳統)?(食品|食物)?", lambda m: (m.group(2) or "北美") + "原住民傳統食物", z)
        m = re.match(r"^((?:北美|阿拉斯加)原住民傳統食物)(?!\(|$)([^(]+)(?:\((.*)\))?$", z)
        if m:                                                             # prefix -> into the brackets
            z = f"{m.group(2)}({m.group(1)}{',' + m.group(3) if m.group(3) else ''})"
    z = re.sub(r"(無|未|非)強化", "無添加營養素", z)
    z = re.sub(r"(?<=[(,])(營養)?強化(?=[,)])", "添加營養素", z)
    return z


def main():
    rows = list(csv.DictReader(open(P, encoding="utf-8")))
    n = 0
    for r in rows:
        z = fix(r["key"], r["zh"])
        if z != r["zh"]:
            r["zh"], n = z, n + 1
    with open(P, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["key", "zh", "file"], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"{n} translations changed")


if __name__ == "__main__":
    main()
