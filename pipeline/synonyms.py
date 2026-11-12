"""Synonyms: the same food under different regional words (HK / TW / CN / JA / EN).

Data: pipeline/synonyms.csv (one row per concept; several words per cell, split by "|").
Words with different meanings per region are listed in pipeline/synonyms_ambiguous.csv;
they are matched only in their own region's sources, so each region's meaning is kept.

Runs at the end of every build (after linking rules 1-4), and does two things:

1. Tags foods with concepts (table food_concepts) and adds every word of those concepts
   to foods.search_text, so a search in any region's words finds the food.
   - Chinese: name_zh and alias are read with the columns of the food's region
     (CFS: HK, then CN; TFDA: TW). Longest words are matched first and their characters
     are masked, so 洋蔥 (onion) is never read as 蔥 (spring onion).
   - Japanese (MEXT name_local): a word must be a whole space-separated token,
     so ねぎ is not found inside たまねぎ.
   - English (all sources): whole words, longest first, plural "s"/"es" allowed;
     punctuation is ignored ("Chicken, egg" is the term "chicken egg").

2. Link rule 5: a food with NO English name whose Chinese/Japanese core name is exactly
   one concept word -> foods of other sources whose English name has exactly the words of
   that concept's main English term, with the same cooking state and plausible values.
   -> 'equivalent', confidence 0.8, method 'synonym'.
"""
import csv
import re
from collections import defaultdict
from pathlib import Path

from . import link

CSV = Path(__file__).with_name("synonyms.csv")
REGIONS = {"cfs": ["hk", "cn"], "tfda": ["tw"]}   # source -> Chinese columns, in priority order
LANGS = ("en", "hk", "tw", "cn", "ja")


def load():
    concepts = {}
    with open(CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            concepts[r["concept"]] = {c: [t.strip() for t in r[c].split("|") if t.strip()] for c in LANGS}
    return concepts


def term_maps(concepts):
    """Per Chinese region list and for ja/en: term -> concept. First (priority) region wins."""
    maps = {}
    for src, cols in REGIONS.items():
        m = {}
        for col in cols:
            for c, terms in concepts.items():
                for t in terms[col]:
                    m.setdefault(t, c)
        maps[src] = m
    maps["ja"] = {t: c for c, terms in concepts.items() for t in terms["ja"]}
    maps["en"] = {t.lower(): c for c, terms in concepts.items() for t in terms["en"]}
    return maps


def match_zh(text, m):
    found, text = set(), text or ""
    for t in sorted(m, key=len, reverse=True):
        if t in text:
            found.add(m[t])
            text = text.replace(t, "\0" * len(t))
    return found


def match_ja(text, m):
    tokens = set(re.split(r"[\s\[\]()<>［］（）＜＞、・]+", text or ""))
    return {m[t] for t in tokens if t in m}


def match_en(text, m):
    # punctuation is ignored, so "Chicken, egg, whole" is read as the term "chicken egg"
    found, text = set(), " ".join(re.sub(r"[^a-z' ]+", " ", (text or "").lower()).split())
    for t in sorted(m, key=len, reverse=True):
        pat = r"\b" + re.escape(t) + r"(?:e?s)?\b"
        if re.search(pat, text):
            found.add(m[t])
            text = re.sub(pat, " ", text)
    return found


def core_name(name):
    """Name without bracketed parts and spaces: '青花菜(2021年取樣)' -> '青花菜'."""
    return re.sub(r"[\(（\[［<＜].*?[\)）\]］>＞]|\s", "", name or "")


def run(db):
    concepts = load()
    maps = term_maps(concepts)
    db.execute("DELETE FROM food_concepts")

    tags = defaultdict(set)
    rows = db.execute("SELECT id, source_id, name_en, name_zh, name_local, alias, search_text FROM foods").fetchall()
    for fid, src, en, zh, local, alias, st in rows:
        found = match_en(f"{en or ''} | {alias or ''}" if src not in REGIONS else en, maps["en"])
        if src in REGIONS:
            found |= match_zh(f"{zh or ''} {alias or ''}", maps[src])
        if src == "mext":
            found |= match_ja(local, maps["ja"])
        tags[fid] = found

    updates, concept_rows = [], []
    by_id = {r[0]: r for r in rows}
    for fid, found in tags.items():
        if not found:
            continue
        words = []
        for c in sorted(found):
            concept_rows.append((fid, c))
            for col in LANGS:
                words += concepts[c][col]
        st = by_id[fid][6]
        extra = [w for w in dict.fromkeys(words) if w.lower() not in st.lower()]
        if extra:
            updates.append((st + " || " + " | ".join(extra), fid))
    db.executemany("UPDATE foods SET search_text = ? WHERE id = ?", updates)
    db.executemany("INSERT INTO food_concepts (food_id, concept) VALUES (?, ?)", concept_rows)
    print(f"  Synonyms              {len(concept_rows):>5} concept tags on {len({r[0] for r in concept_rows})} foods"
          f" ({len(concepts)} concepts)")

    links = synonym_links(db, concepts, maps)
    db.executemany("INSERT OR IGNORE INTO food_links (food_id, canonical_id, match_type, confidence, method)"
                   " VALUES (?, ?, ?, ?, ?)", links)
    print(f"  Same food (synonym)   {len(links):>5} links  {len(links)} equivalent")


def synonym_links(db, concepts, maps):
    linked = {r[0] for r in db.execute("SELECT food_id FROM food_links UNION SELECT canonical_id FROM food_links")}
    vals = defaultdict(dict)
    for f, n, v in db.execute("SELECT food_id, nutrient_id, value FROM food_nutrients WHERE value IS NOT NULL "
                              "AND nutrient_id IN ('protein', 'fat', 'carbohydrate', 'water')"):
        vals[f][n] = v

    # targets: foods with English names, keyed by their normalised word set
    targets = defaultdict(list)
    for fid, src, en, desc in db.execute("SELECT id, source_id, name_en, description FROM foods WHERE name_en IS NOT NULL"):
        targets[frozenset(link.name_tokens(en))].append((fid, src, link.cooking_state(en, desc)))

    out = []
    for fid, src, zh, local, desc in db.execute(
            "SELECT id, source_id, name_zh, name_local, description FROM foods WHERE name_en IS NULL"):
        if src in REGIONS:
            c = maps[src].get(core_name(zh))
        elif src == "mext":
            parts = [p for p in re.split(r"\s+", local or "") if p]
            c = maps["ja"].get(parts[0]) if len(parts) == 1 else None
        else:
            c = None
        if not c or not concepts[c]["en"]:
            continue
        state = link.cooking_state(None, desc)
        key = frozenset(link.name_tokens(concepts[c]["en"][0]))
        for tid, tsrc, tstate in targets.get(key, []):
            if tsrc != src and tstate == state and link.plausible(vals[fid], vals[tid]):
                out.append((fid, tid, "equivalent", 0.8, "synonym"))
    return out
