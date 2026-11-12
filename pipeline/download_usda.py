"""Download the newest USDA FoodData Central CSV zips (Foundation Foods, SR Legacy)
into data/raw/usda/.

Run from the project root:   python3 -m pipeline.download_usda

It reads the FDC download page to find the newest file names. If that fails, it
falls back to the known file names below. Existing files are not downloaded again.
A release whose zip has no food.csv / food_nutrient.csv (USDA published one like
that: Foundation 2026-10-29) is deleted and the next older release is used.

Manual alternative: download the two "CSV" zips from
https://fdc.nal.usda.gov/download-datasets and put them in data/raw/usda/.
"""
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw" / "usda"
PAGE = "https://fdc.nal.usda.gov/download-datasets"
BASE = "https://fdc.nal.usda.gov/fdc-datasets/"
UA = {"User-Agent": "food-data-pipeline/1.0"}
REQUIRED = {"food.csv", "food_nutrient.csv", "nutrient.csv"}
MAX_TRIES = 3

PATTERNS = {
    "foundation": r"FoodData_Central_foundation_food_csv_[\d-]+\.zip",
    "sr_legacy": r"FoodData_Central_sr_legacy_food_csv_[\d-]+\.zip",
}
FALLBACK = {
    "foundation": "FoodData_Central_foundation_food_csv_2025-04-24.zip",
    "sr_legacy": "FoodData_Central_sr_legacy_food_csv_2018-04.zip",
}


def candidates():
    """All file names per dataset from the FDC page, newest first (fallback names if the page fails)."""
    try:
        with urllib.request.urlopen(urllib.request.Request(PAGE, headers=UA), timeout=60) as r:
            page = r.read().decode("utf-8", "replace")
    except Exception as e:
        print(f"Cannot read {PAGE} ({e}); using known file names.", file=sys.stderr)
        return {k: [v] for k, v in FALLBACK.items()}
    return {key: sorted(set(re.findall(pat, page)), reverse=True) or [FALLBACK[key]]
            for key, pat in PATTERNS.items()}


def complete(path):
    """A usable FDC CSV zip has the core tables. Some releases are published without them."""
    try:
        names = {Path(n).name for n in zipfile.ZipFile(path).namelist()}
    except zipfile.BadZipFile:
        return False
    return REQUIRED <= names


def download(name):
    dest = OUT / name
    if dest.exists():
        return dest
    tmp = dest.with_suffix(".part")
    print(f"  get  {name} ...", flush=True)
    with urllib.request.urlopen(urllib.request.Request(BASE + name, headers=UA), timeout=300) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    tmp.rename(dest)
    print(f"       {dest.stat().st_size // (1 << 20)} MB")
    return dest


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for key, names in candidates().items():
        for name in names[:MAX_TRIES]:
            path = download(name)
            if complete(path):
                print(f"  use  {name}")
                break
            print(f"  skip {name}: core tables missing ({', '.join(sorted(REQUIRED))}); trying older release")
            path.unlink()
        else:
            raise SystemExit(f"no complete {key} release found in the newest {MAX_TRIES}")


if __name__ == "__main__":
    main()
