"""Download the UK CoFID 2021 workbook into data/raw/cofid/.

Run from the project root:   python3 -m pipeline.download_cofid

The workbook URL is read from the GOV.UK content API for the CoFID page, so a
re-uploaded file is still found. An existing file is not downloaded again.
"""
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw" / "cofid"
API = "https://www.gov.uk/api/content/government/publications/composition-of-foods-integrated-dataset-cofid"
UA = {"User-Agent": "Mozilla/5.0 (food-data-pipeline)"}


def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180) as r:
        return r.read()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / "cofid_2021.xlsx"
    if dest.exists():
        print(f"have {dest.name}")
        return
    atts = json.loads(fetch(API))["details"]["attachments"]
    url = next(a["url"] for a in atts
               if a["url"].endswith(".xlsx") and "Integrated_Dataset" in a["url"])
    data = fetch(url)
    if not data.startswith(b"PK"):
        raise SystemExit(f"{url} is not an xlsx file")
    dest.write_bytes(data)
    print(f"got  {dest.name} ({len(data) // 1024} KB)")


if __name__ == "__main__":
    main()
