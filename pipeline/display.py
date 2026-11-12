"""Display layer: food groups (clusters), the main record of each group, and display names.

Runs at the end of every build, after linking and synonyms. Agreed with the user 2026-11-12.

Clusters: foods joined by 'exact_copy' or 'equivalent' links ('similar' does not join).
Each cluster has one main record (foods.is_primary = 1). Preference by source, for an HK
audience: cfs, tfda, mext, afcd, cofid, usda_fnd, usda_sr, cnf. Search shows main records;
the other members are shown as "other sources" on the detail page.

display_zh (per cluster):
  1. the HK name: name_zh of a CFS member (the main record if it is CFS, else the shortest);
  2. else the HK synonym word, when a member's name is exactly one concept word
     (Chinese/Japanese core name, or English name words), plus the cooking state
     in Chinese when it is not raw, e.g. USDA "Broccoli, boiled" -> 西蘭花(煮);
     for a Chinese name only the matched word is replaced: 青花菜(2021年取樣) -> 西蘭花(2021年取樣);
  3. else the TFDA name_zh;
  4. else NULL (English only).
display_en: the shortest English name in the cluster.
Original names are never changed; they stay in name_zh / name_en / name_local.
"""
import re
from collections import defaultdict

from . import link, synonyms

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
        "SELECT id, source_id, name_en, name_zh, name_local, description FROM foods")}
    rank = {s: i for i, s in enumerate(PRIORITY)}

    def hk_word(fid):
        _, src, en, zh, local, desc = foods[fid]
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

    rows = []
    for members in clusters(db):
        members.sort(key=lambda f: (rank.get(foods[f][1], 99), f))
        main = members[0]
        cfs = [f for f in members if foods[f][1] == "cfs" and foods[f][3]]
        zh = None
        if cfs:
            zh = foods[main][3] if main in cfs else min((foods[f][3] for f in cfs), key=len)
        if not zh:
            zh = next((w for w in map(hk_word, members) if w), None)
        if not zh:
            zh = next((foods[f][3] for f in members if foods[f][1] == "tfda" and foods[f][3]), None)
        ens = [foods[f][2] for f in members if foods[f][2]]
        en = min(ens, key=lambda n: (len(n), n)) if ens else None
        for f in members:
            rows.append((main, int(f == main), zh, en, f))
    db.executemany("UPDATE foods SET cluster_id = ?, is_primary = ?, display_zh = ?, display_en = ? WHERE id = ?", rows)
    n_clusters = sum(r[1] for r in rows)
    print(f"  Display              {n_clusters:>6} main records for {len(rows)} foods; "
          f"{sum(1 for r in rows if r[1] and r[2])} have a Chinese display name")
