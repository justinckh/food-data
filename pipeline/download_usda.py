"""Download the newest USDA FoodData Central CSV zips (Foundation Foods, SR Legacy)
into data/raw/usda/.

Run from the project root:   python3 -m pipeline.download_usda

It reads the FDC download page to find the newest file names. If that fails, it
falls back to the known file names below. Existing files are not downloaded again.

Manual alternative: download the two "CSV" zips from
https://fdc.nal.usda.gov/download-datasets and put them in data/raw/usda/.
"""
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw" / "usda"
PAGE = "https://fdc.nal.usda.gov/download-datasets"
BASE = "https://fdc.nal.usda.gov/fdc-datasets/"
UA = {"User-Agent": "food-data-pipeline/1.0"}

PATTERNS = {
    "foundation": r"FoodData_Central_foundation_food_csv_[\d-]+\.zip",
    "sr_legacy": r"FoodData_Central_sr_legacy_food_csv_[\d-]+\.zip",
}
FALLBACK = {
    "foundation": "FoodData_Central_foundation_food_csv_2025-04-24.zip",
    "sr_legacy": "FoodData_Central_sr_legacy_food_csv_2018-04.zip",
}


def latest_names():
    try:
        with urllib.request.urlopen(urllib.request.Request(PAGE, headers=UA), timeout=60) as r:
            page = r.read().decode("utf-8", "replace")
    except Exception as e:
        print(f"Cannot read {PAGE} ({e}); using known file names.", file=sys.stderr)
        return dict(FALLBACK)
    names = {}
    for key, pat in PATTERNS.items():
        hits = sorted(set(re.findall(pat, page)))
        names[key] = hits[-1] if hits else FALLBACK[key]
    return names


def download(name):
    dest = OUT / name
    if dest.exists():
        print(f"  have {name}")
        return
    tmp = dest.with_suffix(".part")
    print(f"  get  {name} ...", flush=True)
    with urllib.request.urlopen(urllib.request.Request(BASE + name, headers=UA), timeout=300) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    tmp.rename(dest)
    print(f"       {dest.stat().st_size // (1 << 20)} MB")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name in latest_names().values():
        download(name)


if __name__ == "__main__":
    main()
