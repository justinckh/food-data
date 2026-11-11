"""Download the Australian Food Composition Database (AFCD) Release 3 files
into data/raw/afcd/.

Run from the project root:   python3 -m pipeline.download_afcd

The file URLs are fixed for Release 3. For a new release, update RELEASE_PATH
and the file names in pipeline/importers/afcd.py.
Existing files are not downloaded again.
"""
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw" / "afcd"
RELEASE_PATH = "https://www.foodstandards.gov.au/sites/default/files/2025-12/"
FILES = {
    "AFCD Release 3 - Food Details.xlsx": "afcd_r3_food_details.xlsx",
    "AFCD Release 3 - Nutrient profiles.xlsx": "afcd_r3_nutrient_profiles.xlsx",
    "AFCD Release 3 - Nutrient details.xlsx": "afcd_r3_nutrient_details.xlsx",
    "AFCD Release 3 - Food group information.xlsx": "afcd_r3_food_group_information.xlsx",
}
UA = {"User-Agent": "Mozilla/5.0 (food-data-pipeline)"}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for remote, local in FILES.items():
        dest = OUT / local
        if dest.exists():
            print(f"have {local}")
            continue
        url = RELEASE_PATH + urllib.parse.quote(remote)
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
            data = r.read()
        if not data.startswith(b"PK"):
            raise SystemExit(f"{url} is not an xlsx file - the FSANZ site may have changed")
        dest.write_bytes(data)
        print(f"got  {local} ({len(data) // 1024} KB)")


if __name__ == "__main__":
    main()
