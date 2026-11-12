"""Dated names: re-tested versions of the same food, e.g. CFS 菠蘿包 (2002) and 菠蘿包 (2018),
TFDA 青花菜(1999年取樣) and 青花菜(2021年取樣), TFDA 鯔(2月).

- split(name) -> (name without the date, note): '菠蘿包 (2018)' -> ('菠蘿包', '2018').
- Link rule 0 (run by link.run): records of ONE source whose names are equal without the
  date are versions of one food -> 'equivalent' links (method 'version') from each older
  version to the newest. The display step then shows one food with the newest values.
The user asked for names without dates (2026-11-12); the date is kept as foods.sample_note.
"""
import re
from collections import defaultdict

# A date token inside brackets: 2018 / 2018年 / 2021年取樣 / 2020取樣 / 2月 / 12月取樣
# (TFDA has typos such as "20205年取樣", so a 5-digit year is accepted when 取樣/年 follows.)
TOKEN = re.compile(r"^\s*(?:((?:19|20)\d{2})\s*年?\s*(?:取樣)?|((?:19|20)\d{3})\s*年\s*取樣|(\d{1,2})\s*月\s*(?:取樣)?)\s*$")
# A sampling note with a missing bracket: "白芝麻(熟)2022年取樣)"
LOOSE = re.compile(r"\s*[\(（]?\s*((?:19|20)\d{2,3})\s*年取樣\s*[\)）]?")
BRACKET = re.compile(r"\s*[\(（]([^\(\)（）]*)[\)）]")


def split(name):
    """Remove date tokens from bracketed parts; keep the other parts.
    '菠蘿包 (2018)' -> ('菠蘿包', '2018'); '鯔(12月,雄魚)' -> ('鯔(雄魚)', '12月')."""
    if not name:
        return name, None
    notes = []

    def fix(m):
        parts = [p for p in re.split(r"[,，、]", m.group(1))]
        keep = []
        for part in parts:
            t = TOKEN.match(part)
            if t:
                notes.append(t.group(1) or (t.group(2) or "")[:4] or f"{t.group(3)}月")
            else:
                keep.append(part.strip())
        if len(keep) == len(parts):
            return m.group(0)
        keep = [k for k in keep if k]
        return f"({','.join(keep)})" if keep else ""

    out = BRACKET.sub(fix, name).strip()
    m = LOOSE.search(out)
    if m:
        notes.append(m.group(1)[:4])
        out = (out[:m.start()] + out[m.end():]).strip()
    return (out, " ".join(notes)) if notes else (name, None)


def year(note):
    m = re.search(r"(?:19|20)\d{2}", note or "")
    return int(m.group(0)) if m else 0


def near_identical(a, b):
    """Same food re-tested with almost the same result (agreed with the user 2026-11-12):
    energy within 5 %, and protein, fat, carbohydrate within 1 g or 10 %."""
    ea, eb = a.get("energy_kcal"), b.get("energy_kcal")
    if ea is None or eb is None or abs(ea - eb) > 0.05 * max(ea, eb):
        return False
    for k in ("protein", "fat", "carbohydrate"):
        x, y = a.get(k), b.get(k)
        if x is not None and y is not None and abs(x - y) > max(1.0, 0.10 * max(x, y)):
            return False
    return True


def link_versions(db):
    """Older versions -> newest. Near-identical results are 'exact_copy' (hidden on the site);
    clearly different results are 'equivalent' (shown with their year, e.g. 燒鵝 289 -> 420 kcal)."""
    vals = defaultdict(dict)
    for f, n, v in db.execute("SELECT food_id, nutrient_id, value FROM food_nutrients WHERE value IS NOT NULL "
                              "AND nutrient_id IN ('energy_kcal', 'protein', 'fat', 'carbohydrate')"):
        vals[f][n] = v
    groups = defaultdict(list)
    for fid, src, zh, en in db.execute("SELECT id, source_id, name_zh, name_en FROM foods"):
        base_zh, note_zh = split(zh)
        base_en, note_en = split(en)
        note = note_zh or note_en
        key = (src, base_zh) if zh else (src, (base_en or "").lower())
        groups[key].append((fid, note))
    rows = []
    for members in groups.values():
        if len(members) < 2 or not any(n for _, n in members):
            continue
        newest = max(members, key=lambda m: (year(m[1]), m[1] or "", m[0]))[0]
        for fid, _ in members:
            if fid != newest:
                kind = "exact_copy" if near_identical(vals[fid], vals[newest]) else "equivalent"
                rows.append((fid, newest, kind, 1.0, "version"))
    return rows
