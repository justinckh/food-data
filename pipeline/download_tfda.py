"""Download the TFDA food nutrient dataset (8543) CSV zip into data/raw/tfda/.

Run from the project root:   python3 -m pipeline.download_tfda

The file is saved as tfda_nutrients_<YYYY-MM-DD>.csv.zip (download date).
A file for today that already exists is not downloaded again.
"""
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw" / "tfda"
URL = "https://data.fda.gov.tw/data/opendata/export/20/csv"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / f"tfda_nutrients_{date.today().isoformat()}.csv.zip"
    if dest.exists():
        print(f"have {dest.name}")
        return
    tmp = dest.with_suffix(".part")
    print(f"get  {URL} ...", flush=True)
    req = urllib.request.Request(URL, headers={"User-Agent": "food-data-pipeline/1.0"})
    with urllib.request.urlopen(req, timeout=300) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    if not zipfile.is_zipfile(tmp):
        tmp.unlink()
        raise SystemExit("download is not a zip file - the TFDA export may have changed")
    tmp.rename(dest)
    print(f"     {dest.name} ({dest.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
