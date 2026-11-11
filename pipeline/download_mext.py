"""Download the Japan MEXT food composition tables into data/raw/mext/.

Run from the project root:   python3 -m pipeline.download_mext

- Main table: the first "第2章（データ）" Excel link on the MEXT page for the
  8th edition 2023 supplement. Saved as mext_sftc8_2023_main_<YYYYMMDD>.xlsx, where
  the date is MEXT's upload date taken from the file URL.
- English names: the 7th edition (2015) English table. Saved as mext_sftc7_2015_english.xlsx.
Existing files are not downloaded again.
"""
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw" / "mext"
SITE = "https://www.mext.go.jp"
PAGE = SITE + "/a_menu/syokuhinseibun/mext_00001.html"
ENGLISH = SITE + "/component/english/__icsFiles/afieldfile/2017/12/25/1374049_1r12_1.xlsx"
UA = {"User-Agent": "Mozilla/5.0 (food-data-pipeline)"}


def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return r.read()


def save(url, dest):
    if dest.exists():
        print(f"have {dest.name}")
        return
    data = fetch(url)
    if not data.startswith(b"PK"):
        raise SystemExit(f"{url} is not an xlsx file - the MEXT page may have changed")
    dest.write_bytes(data)
    print(f"got  {dest.name} ({len(data) // 1024} KB)")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    page = fetch(PAGE).decode("utf-8", "replace")
    m = re.search(r'href="([^"]+\.xlsx)"[^>]*>\s*・?第2章（データ）', page)
    if not m:
        raise SystemExit("main table link not found on the MEXT page")
    url = m.group(1) if m.group(1).startswith("http") else SITE + m.group(1)
    d = re.search(r"/(\d{8})-", url)
    save(url, OUT / f"mext_sftc8_2023_main_{d.group(1) if d else 'latest'}.xlsx")
    save(ENGLISH, OUT / "mext_sftc7_2015_english.xlsx")


if __name__ == "__main__":
    main()
