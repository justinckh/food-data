"""Display layer: food groups (clusters), the main record of each group, and display names.

Runs at the end of every build, after linking and synonyms. Agreed with the user 2026-11-12.

Clusters: foods joined by 'exact_copy' or 'equivalent' links ('similar' does not join).
Each cluster has one main record (foods.is_primary = 1). Preference by source, for an HK
audience: cfs, tfda, mext, afcd, cofid, usda_fnd, usda_sr, cnf. Search shows main records;
the other members are shown as "other sources" on the detail page.

display_zh (per cluster):
  1. the HK name: name_zh of a CFS member (the main record if it is CFS, else the shortest);
     for CFS records copied from the China table, a Mainland word is shown as the HK word
     (鱷梨 -> 牛油果). Every CFS record keeps its own name, even inside a group;
  2. else the HK synonym word, when a member's name is exactly one concept word
     (Chinese/Japanese core name, or English name words), plus the cooking state
     in Chinese when it is not raw, e.g. USDA "Broccoli, boiled" -> 西蘭花(煮);
     for a Chinese name only the matched word is replaced: 青花菜(2021年取樣) -> 西蘭花(2021年取樣);
  3. else the TFDA name_zh;
  4. else the machine translation of the English name (or the Japanese name) from
     pipeline/translations_zh.csv (pipeline/translate_prep.py); foods.zh_mt = 1;
  5. else NULL (English only).
display_en: the shortest English name in the cluster.
Original names are never changed; they stay in name_zh / name_en / name_local.
"""
import csv
import re
from collections import defaultdict
from pathlib import Path

from . import link, synonyms, versions

TRANSLATIONS = Path(__file__).resolve().parent / "translations_zh.csv"
PRIORITY = ["cfs", "tfda", "mext", "afcd", "cofid", "usda_fnd", "usda_sr", "cnf"]
# Preparation words ignored when matching an English name to a synonym word (display only;
# the linking rules keep their reviewed word lists).
PREP = {"drained", "unprepared", "prepared", "fresh", "boneless", "peeled", "unpeeled", "trimmed",
        "untrimmed", "unenriched", "enriched", "unsalted", "cooked", "uncooked", "ready", "eat",
        "variety", "commercial", "skin"}
STATE_ZH = {"boiled": "煮", "steamed": "蒸", "baked": "焗", "roasted": "烤", "fried": "炸",
            "grilled": "燒烤", "microwaved": "微波", "dried": "乾", "canned": "罐頭", "frozen": "冷凍",
            "cooked": "熟"}


def clusters(db):
    parent = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in db.execute("SELECT food_id, canonical_id FROM food_links WHERE match_type IN ('exact_copy', 'equivalent')"):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    groups = defaultdict(list)
    for fid, in db.execute("SELECT id FROM foods"):
        groups[find(fid)].append(fid)
    return list(groups.values())


def run(db):
    concepts = synonyms.load()
    maps = synonyms.term_maps(concepts)
    en_concept = {frozenset(link.name_tokens(t)): c for c, terms in concepts.items() for t in terms["en"]}
    foods = {r[0]: r for r in db.execute(
        "SELECT id, source_id, name_en, name_zh, name_local, description, origin_source FROM foods")}
    rank = {s: i for i, s in enumerate(PRIORITY)}

    def hk_word(fid):
        _, src, en, zh, local, desc, _origin = foods[fid]
        c = None
        if src in synonyms.REGIONS:
            core = synonyms.core_name(zh)
            c = maps[src].get(core)
            if c and concepts[c]["hk"]:
                # keep everything around the matched word: 青花菜(2021年取樣) -> 西蘭花(2021年取樣)
                return zh.replace(core, concepts[c]["hk"][0], 1)
        if not c and src == "mext" and local and len(local.split()) == 1:
            c = maps["ja"].get(local)
        state = link.cooking_state(en, desc)
        if not c and en:
            # "oil-roasted" / "dry-roasted" describe roasting, not oil
            plain = re.sub(r"\b(?:oil|dry)-roasted\b", "roasted", en, flags=re.I)
            c = en_concept.get(frozenset(link.name_tokens(plain) - PREP))
        if not c or not concepts[c]["hk"]:
            return None
        word = concepts[c]["hk"][0]
        extra = [STATE_ZH[s] for s in sorted(state) if s in STATE_ZH]
        if len(extra) > 1 and "熟" in extra:      # "cooked" adds nothing next to "boiled"
            extra.remove("熟")
        return f"{word}({','.join(extra)})" if extra else word

    cn_to_hk = {t: terms["hk"][0] for terms in concepts.values() if terms["hk"]
                for t in terms["cn"] if t not in terms["hk"]}

    def cfs_name(fid):
        """A CFS record's own name. Records copied from the China table use Mainland words
        (鱷梨); show the HK word (牛油果). HK's own records already use HK words."""
        zh = foods[fid][3]
        if zh and foods[fid][6] == synonyms.CHINA:
            core = synonyms.core_name(zh)
            if core in cn_to_hk:
                return zh.replace(core, cn_to_hk[core], 1)
        return zh

    # sampling dates are removed from shown names (user request 2026-11-12) and kept as a note
    note = {}
    for fid, (_, _, en, zh, *_rest) in foods.items():
        note[fid] = versions.split(zh)[1] or versions.split(en)[1]

    def nodate(name):
        return versions.split(name)[0] if name else name

    mt = {}
    if TRANSLATIONS.exists():
        with open(TRANSLATIONS, encoding="utf-8") as f:
            mt = {r["key"]: r["zh"] for r in csv.DictReader(f)}

    rows = []
    for members in clusters(db):
        # source preference, then the newest version (dated re-tests), then id
        members.sort(key=lambda f: (rank.get(foods[f][1], 99), -versions.year(note[f]), f))
        main = members[0]
        cfs = [f for f in members if foods[f][1] == "cfs" and foods[f][3]]
        zh = None
        if cfs:
            zh = cfs_name(main) if main in cfs else min((cfs_name(f) for f in cfs), key=len)
        if not zh:
            zh = next((w for w in map(hk_word, members) if w), None)
        if not zh:
            zh = next((foods[f][3] for f in members if foods[f][1] == "tfda" and foods[f][3]), None)
        # TFDA English names can be synonym lists ("Sea mullet; River mullet; ..."): first name only
        ens = [foods[f][2].split(";")[0].strip() for f in members if foods[f][2] and foods[f][2].split(";")[0].strip()]
        en = min(ens, key=lambda n: (len(n), n)) if ens else None
        is_mt = 0
        if not zh:
            # same key as translate_prep: the shown English name, else the Japanese name
            zh = mt.get(nodate(en) or foods[main][4])
            is_mt = int(zh is not None)
        for f in members:
            # HK records always keep their own (HK) name; other records show the group name
            own_zh = cfs_name(f) if foods[f][1] == "cfs" and foods[f][3] else zh
            own_en = foods[f][2] if foods[f][1] == "cfs" and foods[f][2] else en
            own_mt = 0 if foods[f][1] == "cfs" and foods[f][3] else is_mt
            rows.append((main, int(f == main), nodate(own_zh), nodate(own_en), note[f], own_mt, f))
    db.executemany("UPDATE foods SET cluster_id = ?, is_primary = ?, display_zh = ?, display_en = ?, sample_note = ?, "
                   "zh_mt = ? WHERE id = ?", rows)
    # translated names are searchable too
    db.execute("UPDATE foods SET search_text = search_text || ' ' || lower(display_zh) "
               "WHERE zh_mt = 1 AND instr(search_text, lower(display_zh)) = 0")   # display runs twice
    n_clusters = sum(r[1] for r in rows)
    print(f"  Display              {n_clusters:>6} main records for {len(rows)} foods; "
          f"{sum(1 for r in rows if r[1] and r[2])} have a Chinese display name "
          f"({sum(1 for r in rows if r[1] and r[5])} machine-translated)")
