#!/usr/bin/env python3
"""Scrape the CFS (Hong Kong Centre for Food Safety) Nutrient Information Inquiry
food calculator: https://www.cfs.gov.hk/tc_chi/nutrient/fc-search1.php

Flow (all plain HTML form POSTs, no JS/API needed):
  fc-search1.php                         -> 24 food groups (fg_id)
  fc-nutrientvalue.php  fg_id, fsg_id=-1 -> every food_id in a group
  fc-myreport.php       food_id          -> full per-100g nutrient sheet

Detail pages are cached in cache/ so the run can be stopped and resumed.
Output: cfs_foods.csv (one row per food, one column per nutrient).
"""
import csv
import html
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BASE = "https://www.cfs.gov.hk/tc_chi/nutrient/"
ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "cache"
OUT = ROOT / "cfs_foods.csv"
WORKERS = 4
DELAY = 0.3  # seconds between requests per worker; be polite to a gov server

SOURCE_CODES = {
    "A": "USDA FoodData Central",
    "B": "China CDC Food Composition Table (CFC2002Ed2)",
    "C": "CFS Food Research Laboratory (FRL)",
    "D": "Food Standards Australia New Zealand (FSANZ)",
    "E": "Mahidol University Thai FCD 2025",
}


def post(page, data, retries=4):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(BASE + page, data=body, headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            if attempt == retries - 1:
                raise
            print(f"  retry {page} {data.get('food_id', '')}: {e}", file=sys.stderr)
            time.sleep(2 ** attempt)


def text(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def get_groups():
    t = post("fc-search1.php", {})
    return re.findall(r"tosubmit\('(\d+)','([^']*)','([^']*)'\)", t)


def get_food_ids(fg_id):
    t = post("fc-nutrientvalue.php", {"fg_id": fg_id, "fsg_id": "-1", "forFC": "1", "inShortMode": "1"})
    ids, source = [], {}
    for m in re.finditer(r"tosubmit\('%s','-1','([^']+)'\)(.*?)</tr>" % fg_id, t, re.S):
        fid = m.group(1)
        if fid in source:
            continue
        ids.append(fid)
        # first single-letter cell after the name is the source code
        cells = [text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", m.group(2), re.S)]
        source[fid] = next((c for c in cells if re.fullmatch(r"[A-Z]", c)), "")
    return ids, source


def get_report(fg_id, food_id):
    f = CACHE / f"{food_id}.html"
    if f.exists():
        return f.read_text("utf-8")
    t = post("fc-myreport.php", {"fg_id": fg_id, "fsg_id": "-1", "food_id": food_id, "forFC": "1"})
    f.write_text(t, "utf-8")
    time.sleep(DELAY)
    return t


def split_zh_en(s):
    m = re.match(r"(.*?)\s*\(([^()]*(?:\([^()]*\)[^()]*)*)\)\s*$", s)
    return (m.group(1).strip(), m.group(2).strip()) if m else (s, "")


def parse_report(t):
    x = text(re.sub(r"(?s)<script.*?</script>", "", t))

    def field(label, stop):
        m = re.search(label + r"\s*[:：]\s*(.*?)\s*(?:" + stop + ")", x)
        return m.group(1).strip() if m else ""

    row = {}
    row["group_zh"], row["group_en"] = split_zh_en(field("食物類別", "食物細分類別"))
    row["subgroup_zh"], row["subgroup_en"] = split_zh_en(field("食物細分類別", "食物名稱"))
    name = field("食物名稱", "資料來源")
    name, _, alias = name.partition(" 別名:")
    row["name_zh"], row["name_en"] = split_zh_en(name)
    row["alias"] = alias.strip()
    row["source"] = field("資料來源", "分量")
    row["serving"] = field("分量", "對照分量|請輸入")
    row["reference_serving"] = field("對照分量", "請輸入") if "對照分量" in x else ""

    table = t[t.find("<th>營養</th>"):]
    table = table[: table.find("</table>")]
    table = re.sub(r"(?s)<!--.*?-->", "", table)  # drop commented-out rows (e.g. alcohol)
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S):
        tds = [text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(tds) == 3:
            name, unit, val = tds
            row[f"{name.rstrip('*')} ({unit})"] = val
    return row


def main():
    CACHE.mkdir(exist_ok=True)
    groups = get_groups()
    print(f"{len(groups)} food groups")

    jobs = []  # (fg_id, food_id, source_code)
    for fg_id, zh, en in groups:
        ids, src = get_food_ids(fg_id)
        print(f"  {fg_id} {en.strip():40s} {len(ids)} foods")
        jobs += [(fg_id, fid, src[fid]) for fid in ids]
        time.sleep(DELAY)
    print(f"{len(jobs)} foods total; fetching detail pages...")

    def work(job):
        fg_id, fid, code = job
        row = {"food_id": fid, "fg_id": fg_id, "source_code": code}
        row.update(parse_report(get_report(fg_id, fid)))
        return row

    rows = []
    with ThreadPoolExecutor(WORKERS) as ex:
        for i, row in enumerate(ex.map(work, jobs), 1):
            rows.append(row)
            if i % 100 == 0:
                print(f"  {i}/{len(jobs)}")

    cols = []
    for r in rows:
        cols += [k for k in r if k not in cols]
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:  # BOM so Excel reads Chinese
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows x {len(cols)} cols -> {OUT}")


if __name__ == "__main__":
    main()
