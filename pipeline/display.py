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

SALTED = re.compile(r"\bwith (?:added )?salt\b|\bsalt added\b", re.I)
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


# Taiwan (TFDA) words -> Hong Kong words in shown names (user request 2026-11-12). Longest first.
# Original names stay in name_zh. '平均值' (TFDA: average of several samples) is dropped.
TW_HK = [
    ("櫻桃小番茄", "車厘茄"), ("小番茄", "車厘茄"), ("奶油萵苣", "牛油生菜"), ("萵苣", "生菜"),
    ("櫻桃蘿蔔", "櫻桃蘿蔔"), ("奶油南瓜", "牛油果南瓜"), ("奶油白菜", "奶白菜"),
    ("三節翅", "雞全翼"), ("二節翅", "雞中翼"), ("翅腿", "雞翼根"), ("土雞", "走地雞"),
    ("綠花椰菜", "西蘭花"), ("白花椰菜", "椰菜花"), ("花椰菜", "椰菜花"), ("高麗菜", "椰菜"),
    ("馬鈴薯", "薯仔"), ("洋芋", "薯仔"), ("地瓜", "番薯"), ("玉米", "粟米"), ("鳳梨", "菠蘿"),
    ("酪梨", "牛油果"), ("草莓", "士多啤梨"), ("櫻桃", "車厘子"), ("奇異果", "奇異果"),
    ("鮭魚", "三文魚"), ("鮪魚", "吞拿魚"), ("培根", "煙肉"), ("起司", "芝士"), ("乳酪", "芝士"),
    ("優格", "乳酪"), ("優酪乳", "乳酪飲品"), ("巧克力", "朱古力"), ("冰淇淋", "雪糕"),
    ("義大利麵", "意粉"), ("花枝", "墨魚"), ("透抽", "魷魚"), ("小卷", "魷魚仔"), ("豬五花", "豬腩肉"),
    ("五花肉", "腩肉"), ("鮮奶油", "忌廉"), ("奶油", "牛油"), ("美乃滋", "沙律醬"), ("番茄醬", "茄汁"),
    ("青江菜", "小棠菜"), ("空心菜", "通菜"), ("地瓜葉", "番薯葉"), ("豌豆苗", "豆苗"),
    # review of all TFDA shown names, 2026-11-13. Entries that map to themselves are guards
    # (the longer word wins, so the shorter rule does not change it).
    # corrections: 奶油(液態) is cream; 洋芋片 is 薯片 (not 薯仔片); HK sells 鳳梨酥 by that name
    ("奶油(液態)", "忌廉"), ("人造奶油", "植物牛油"), ("洋芋片", "薯片"), ("馬鈴薯片", "薯片"),
    ("馬鈴薯條", "薯條"), ("馬鈴薯粉", "薯粉"), ("鳳梨酥", "鳳梨酥"), ("嫩莖萵苣", "萵筍"),
    ("蘿蔓萵苣", "羅馬生菜"), ("蘿蔓", "羅馬"),
    # vegetables
    ("結球白菜", "紹菜"), ("青花菜筍", "西蘭花苗"), ("青花菜", "西蘭花"), ("羽衣甘藍", "羽衣甘藍"),
    ("球莖甘藍", "椰菜頭"), ("紫色甘藍", "紫椰菜"), ("酸甘藍菜", "酸椰菜"), ("甘藍芽", "甘藍芽"),
    ("甘藍", "椰菜"), ("甘藷葉", "番薯葉"), ("甘藷", "番薯"), ("甘薯", "番薯"), ("胡蘿蔔素", "胡蘿蔔素"), ("胡蘿蔔", "甘筍"),
    ("紅蘿蔔", "甘筍"), ("花胡瓜", "青瓜"), ("小胡瓜", "小青瓜"), ("櫛瓜", "翠玉瓜"), ("甜椒", "燈籠椒"),
    ("敏豆", "四季豆"), ("菜豆", "豆角"), ("甜豌豆莢", "蜜糖豆"), ("豌豆莢", "荷蘭豆"), ("豌豆仁", "青豆"),
    ("豌豆芽", "豆苗"), ("油菜心", "菜心"), ("芥藍菜", "芥蘭"), ("芥藍芽", "芥蘭苗"), ("西洋芹菜", "西芹"),
    ("洋香菜", "番茜"), ("洋菇", "蘑菇"), ("金針菇", "金菇"), ("雞腿菇", "雞腿菇"), ("荸薺", "馬蹄"),
    ("豆薯", "沙葛"), ("稜角絲瓜", "勝瓜"), ("隼人瓜苗", "龍鬚菜"), ("隼人瓜", "合掌瓜"),
    ("根菾菜根", "紅菜頭"), ("蕃茄醬", "茄汁"), ("小蕃茄", "車厘茄"),
    # fruit
    ("芭樂", "番石榴"), ("釋迦", "番荔枝"), ("柳橙", "橙"), ("甜橙", "橙"), ("葡萄柚", "西柚"),
    ("萊姆", "青檸"), ("百香果", "熱情果"), ("紅龍果", "火龍果"), ("西洋梨", "啤梨"), ("李子", "布冧"),
    ("蜜李", "西梅"), ("蔓越莓", "小紅莓"), ("洋香瓜", "蜜瓜"),
    # milk products
    ("凝態發酵乳", "乳酪"), ("濃稠發酵乳", "乳酪飲品"), ("稀釋發酵乳", "乳酸菌飲品"),
    ("乳酸飲料", "乳酸菌飲品"), ("保久乳", "UHT奶"), ("鮮乳", "鮮奶"), ("調味乳", "調味奶"),
    ("羊乳", "羊奶"), ("淡煉乳", "淡奶"), ("煉乳", "煉奶"), ("乾酪", "芝士"), ("冰棒", "雪條"),
    # bakery, snacks, drinks
    ("土司", "方包"), ("吐司", "方包"), ("可頌", "牛角包"), ("披薩", "薄餅"), ("千島沙拉醬", "千島醬"),
    ("沙拉", "沙律"), ("甜甜圈", "冬甩"), ("蛋塔", "蛋撻"), ("蘇打", "梳打"), ("三明治", "三文治"),
    ("菠蘿麵包", "菠蘿包"), ("蜂蜜蛋糕", "長崎蛋糕"), ("牛軋糖", "鳥結糖"), ("咖啡凍", "咖啡啫喱"),
    ("果凍", "啫喱"), ("仙草凍", "涼粉"), ("夏威夷豆", "夏威夷果仁"), ("葵瓜子", "葵花籽"),
    ("甘扁桃仁", "杏仁"), ("榛果", "榛子"), ("奇亞子", "奇亞籽"), ("西谷米", "西米"), ("沙士", "沙示"),
    # noodles, dumplings, grains
    ("義大利", "意大利"), ("義式", "意式"), ("通心麵", "通心粉"), ("烏龍麵", "烏冬"), ("冬粉", "粉絲"),
    ("餛飩", "雲吞"), ("春捲", "春卷"), ("蛋捲", "蛋卷"), ("薏仁", "薏米"), ("高梁", "高粱"), ("稉", "粳"),
    # meat, eggs, tofu
    ("沙朗肉排", "西冷扒"), ("沙朗", "西冷"), ("腓力牛排", "牛柳扒"), ("菲力肉排", "柳扒"), ("牛排", "牛扒"), ("雞排", "雞扒"),
    ("豬排", "豬扒"), ("羊排", "羊扒"), ("帶骨牛小排", "牛仔骨"), ("豬小里肌", "豬柳"),
    ("豬大里肌", "豬肉眼"), ("里肌", "里脊"), ("豬絞肉", "免治豬肉"), ("雞絞肉", "免治雞肉"),
    ("腹脇", "腩"), ("腹脅", "腩"), ("豬肩胛肉", "豬梅頭肉"), ("豬肩胛排", "豬梅頭扒"), ("豬前腳", "豬手"),
    ("豬蹄膀", "豬肘"), ("豬腎", "豬腰"), ("雞腿", "雞髀"), ("雞翅", "雞翼"), ("胗", "腎"),
    ("雞滷蛋", "滷水雞蛋"), ("鵪鶉滷蛋", "滷水鵪鶉蛋"), ("滷蛋", "滷水蛋"), ("滷牛筋", "滷水牛筋"), ("滷豬腳", "滷水豬腳"), ("嫩豆腐", "滑豆腐"), ("豆干", "豆腐乾"),
    # fish and seafood
    ("吳郭魚", "羅非魚"), ("台灣鯛魚", "羅非魚"), ("台灣鯛", "羅非魚"), ("虱目魚", "遮目魚"),
    ("白帶魚", "牙帶"), ("魩仔魚", "白飯魚"), ("綠殼菜蛤", "青口"), ("蟹味棒", "蟹柳"), ("貢丸", "豬肉丸"),
    ("干貝", "瑤柱"), ("牡蠣干", "蠔豉"), ("蚵仔白菜", "蚵仔白菜"), ("蚵仔煎", "蚵仔煎"), ("蚵", "蠔"), ("鮪排", "吞拿魚排"),
    ("大目鮪", "大眼吞拿魚"), ("干", "乾"),
    # sauces and seasonings
    ("醬油", "豉油"), ("烏醋", "黑醋"), ("香油", "麻油"), ("高湯塊", "湯粒"), ("山葵", "芥辣"),
    ("黃芥茉", "黃芥末"), ("冷凍,", "冷凍"),
]
TW_HK.sort(key=lambda p: -len(p[0]))


def tw_hk(name):
    if not name:
        return name
    out, i = [], 0
    while i < len(name):                      # one pass, longest match first (no double replacing)
        for tw, hk in TW_HK:
            if name.startswith(tw, i):
                out.append(hk)
                i += len(tw)
                break
        else:
            out.append(name[i])
            i += 1
    return "".join(out).replace("平均值", "").strip()


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

    # records linked to another record of the SAME source (older version, TFDA sample, re-release,
    # partial release, salted twin) are never the main record when their target is in the group
    secondary = {a for a, b in db.execute("SELECT food_id, canonical_id FROM food_links WHERE match_type != 'similar'")
                 if foods[a][1] == foods[b][1]}
    # English name: not from a salted twin or a re-released/partial record ('..., with salt' is shorter)
    twins = {f for f, in db.execute("SELECT food_id FROM food_links WHERE method IN ('salt', 'same_source', "
                                    "'same_source_sparse')")}
    has_energy = {f for f, in db.execute("SELECT food_id FROM food_nutrients WHERE nutrient_id = 'energy_kcal' "
                                         "AND value IS NOT NULL")}

    # reviewed shown names for foods that had the same name as a different food (name_fixes.csv)
    rename = {f: z for f, z in link.load_fixes("rename") if f in foods}

    rows = []
    for members in clusters(db):
        # source preference, then not secondary, then with energy, then the newest version
        # (dated re-tests), then id
        members.sort(key=lambda f: (rank.get(foods[f][1], 99), f in secondary, f not in has_energy,
                                    "平均值" not in (foods[f][3] or ""), -versions.year(note[f]), f))
        main = members[0]
        cfs = [f for f in members if foods[f][1] == "cfs" and foods[f][3]]
        zh = None
        if cfs:
            zh = cfs_name(main) if main in cfs else min((cfs_name(f) for f in cfs), key=len)
        if not zh and foods[main][1] == "tfda" and foods[main][3]:
            # Taiwan record: keep its own details, change only the words (TW -> HK)
            z = foods[main][3].replace("平均值", "")
            core = synonyms.core_name(z)
            c = maps["tfda"].get(core)
            if c and concepts[c]["hk"]:
                z = z.replace(core, concepts[c]["hk"][0], 1)
            zh = tw_hk(z)
            converted = True
        else:
            converted = False
        if not zh:
            zh = next((w for w in map(hk_word, members) if w), None)
        if not zh:
            zh = next((foods[f][3] for f in members if foods[f][1] == "tfda" and foods[f][3]), None)
        if zh and foods[main][1] == "tfda" and not converted:
            # only once: TW_HK is not idempotent (優格 -> 乳酪, 乳酪 -> 芝士)
            zh = tw_hk(zh)
        # TFDA English names can be synonym lists ("Sea mullet; River mullet; ..."): first name only
        salted = SALTED.search(foods[main][2] or "")
        named = [f for f in members if f not in twins and (salted or not SALTED.search(foods[f][2] or ""))] or members
        ens = [foods[f][2].split(";")[0].strip() for f in named if foods[f][2] and foods[f][2].split(";")[0].strip()]
        en = min(ens, key=lambda n: (len(n), n)) if ens else None
        is_mt = 0
        fixed = next((rename[f] for f in members if f in rename and foods[f][1] != "cfs"), None)
        if main in rename:
            fixed = rename[main]
        if fixed:
            zh = fixed
        if not zh:
            # same key as translate_prep: the shown English name, else the Japanese name
            zh = mt.get(nodate(en) or foods[main][4])
            is_mt = int(zh is not None)
        for f in members:
            # HK records always keep their own (HK) name; other records show the group name
            own_zh = cfs_name(f) if foods[f][1] == "cfs" and foods[f][3] else zh
            if foods[f][1] == "cfs" and f in rename:
                own_zh = rename[f]
            own_en = foods[f][2] if foods[f][1] == "cfs" and foods[f][2] else en
            own_mt = 0 if (foods[f][1] == "cfs" and foods[f][3]) or fixed else is_mt
            rows.append((main, int(f == main), nodate(own_zh), nodate(own_en), note[f], own_mt, f))
    db.executemany("UPDATE foods SET cluster_id = ?, is_primary = ?, display_zh = ?, display_en = ?, sample_note = ?, "
                   "zh_mt = ? WHERE id = ?", rows)
    # shown names are searchable too (translations, TW -> HK words such as 雞全翼)
    db.execute("UPDATE foods SET search_text = search_text || ' ' || lower(display_zh) "
               "WHERE display_zh IS NOT NULL AND instr(search_text, lower(display_zh)) = 0")   # shown names (HK words, translations)
    same = db.execute("SELECT count(*), coalesce(sum(n), 0) FROM (SELECT count(*) n FROM foods WHERE is_primary = 1 "
                      "AND display_zh IS NOT NULL GROUP BY display_zh HAVING n > 1)").fetchone()
    print(f"  Shown names          {same[0]:>6} names are shown on more than one food group ({same[1]} groups); "
          f"name_fixes.csv: {len(rename)} renames")
    n_clusters = sum(r[1] for r in rows)
    print(f"  Display              {n_clusters:>6} main records for {len(rows)} foods; "
          f"{sum(1 for r in rows if r[1] and r[2])} have a Chinese display name "
          f"({sum(1 for r in rows if r[1] and r[5])} machine-translated)")
