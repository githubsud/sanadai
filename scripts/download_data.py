"""Download raw datasets into data/raw/ (untouched). Idempotent: skips files that already exist.

Sources (see SOURCES.md):
  - Tanzil Quran text: uthmani + simple-clean, XML format (CC BY 3.0, verbatim only). XML keeps the Basmala as a
    separate attribute of verse 1 (the TXT format prefixes it to the verse text).
  - Tanzil translation en.sahih (Saheeh International; non-commercial use)
  - fawazahmed0/hadith-api (Unlicense): Arabic + English editions with gradings
"""

import argparse
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"

TANZIL_TEXT = (
    "https://tanzil.net/pub/download/index.php?marks=true&sajdah=true&rub=false&tatweel=true"
    "&quranType={qtype}&outType=xml&agree=true"
)
TANZIL_TRANS = "https://tanzil.net/trans/?transID={tid}&type=txt-2"

HADITH_API = "https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@1"
HADITH_API_FALLBACK = "https://raw.githubusercontent.com/fawazahmed0/hadith-api/1"
COLLECTIONS = ["bukhari", "muslim", "abudawud", "tirmidhi", "nasai", "ibnmajah", "malik",
               "nawawi", "qudsi", "dehlawi"]


def fetch(client: httpx.Client, urls: list[str], dest: Path, force: bool) -> None:
    if dest.exists() and dest.stat().st_size > 0 and not force:
        print(f"  skip  {dest.relative_to(ROOT)} (exists)")
        return
    last_err: Exception | None = None
    for url in urls:
        for attempt in range(3):
            try:
                r = client.get(url)
                r.raise_for_status()
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(r.content)
                print(f"  ok    {dest.relative_to(ROOT)} ({len(r.content) / 1e6:.1f} MB)")
                return
            except httpx.HTTPError as e:
                last_err = e
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"failed to download {dest.name}: {last_err}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-download existing files")
    args = ap.parse_args()

    headers = {"User-Agent": "SanadAI-dataset-downloader/0.1 (research; non-commercial)"}
    with httpx.Client(timeout=120, follow_redirects=True, headers=headers) as client:
        print("Tanzil Quran text")
        for qtype in ("uthmani", "simple-clean"):
            fetch(client, [TANZIL_TEXT.format(qtype=qtype)], RAW / "tanzil" / f"quran-{qtype}.xml", args.force)
        fetch(client, ["https://tanzil.net/res/text/metadata/quran-data.xml"],
              RAW / "tanzil" / "quran-data.xml", args.force)
        print("Tanzil translation")
        fetch(client, [TANZIL_TRANS.format(tid="en.sahih")], RAW / "tanzil" / "en.sahih.txt", args.force)

        print("fawazahmed0/hadith-api")
        fetch(client, [f"{HADITH_API}/info.min.json", f"{HADITH_API_FALLBACK}/info.min.json"],
              RAW / "hadith-api" / "info.json", args.force)
        for col in COLLECTIONS:
            for lang in ("ara", "eng"):
                name = f"{lang}-{col}"
                urls = [f"{HADITH_API}/editions/{name}.min.json", f"{HADITH_API}/editions/{name}.json",
                        f"{HADITH_API_FALLBACK}/editions/{name}.min.json"]
                fetch(client, urls, RAW / "hadith-api" / f"{name}.json", args.force)
    print("done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
