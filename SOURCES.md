# SOURCES — datasets and services used by SanadAI

All raw files are downloaded by `scripts/download_data.py` into `data/raw/` and kept **untouched**.
Raw data is not committed to the repository; the script reproduces it.

| # | Source | URL | License / terms | Version / date retrieved | Used for |
|---|--------|-----|-----------------|--------------------------|----------|
| 1 | Tanzil Quran text — Uthmani | https://tanzil.net/download | CC BY 3.0; verbatim copies only, **changing is not allowed**; credit Tanzil + link to tanzil.net | Uthmani v1.1, retrieved 2026-09-24 | Display of verses (verbatim) |
| 2 | Tanzil Quran text — Simple Clean | https://tanzil.net/download | CC BY 3.0 (same terms) | Simple Clean v1.1, retrieved 2026-09-24 | Normalized matching of verses |
| 3 | Tanzil Quran metadata | https://tanzil.net/res/text/metadata/quran-data.xml | CC BY (per file header) | v1.0, retrieved 2026-09-24 | Surah names (ar/en), ayah counts |
| 4 | Saheeh International English translation (via Tanzil, `en.sahih`) | https://tanzil.net/trans/ | "For non-commercial purposes only; otherwise obtain permission from the translator/publisher." | Last update 2011-04-24, retrieved 2026-09-24 | English meaning of verses (labelled as a translation, never as Quran) |
| 5 | fawazahmed0/hadith-api | https://github.com/fawazahmed0/hadith-api | The Unlicense (public domain) | branch `1`, retrieved 2026-09-24 | Arabic + English hadith text of 10 collections; gradings by named graders (Al-Albani, Shuaib Al-Arnaut, Zubair Ali Zai, Ahmad Shakir, …) |
| 6 | Dorar.net (الدرر السنية) — hadith encyclopedia | https://dorar.net | Public website/API; used lightly with caching and attribution | live, cached in `dorar_cache` | Gradings of weak/fabricated hadith and authentic alternatives |
| 7 | AhmedElTabarani/dorar-hadith-api | https://github.com/AhmedElTabarani/dorar-hadith-api | MIT | main @ 2026-05 | Reference for Dorar endpoints and HTML parsing (ported to Python in `app/sources/dorar.py`) |

## Considered but not used (yet)
| Source | Why not |
|--------|---------|
| AhmedBaset/hadith-json (https://github.com/AhmedBaset/hadith-json) | No license declared in the repository (scraped from sunnah.com). Pending owner decision. |

## Attribution shown in the app
- "Quran text: Tanzil Project — tanzil.net (CC BY 3.0, verbatim)."
- "English translation of meanings: Saheeh International (via Tanzil), non-commercial use."
- "Hadith texts and gradings: fawazahmed0/hadith-api (sunnah.com-derived), graders named per item."
- "Weak/fabricated hadith gradings and alternatives: Dorar.net (الدرر السنية)."

## Notes on derived data
- `text_norm`, `matn_norm`: normalized copies for matching only; display always uses the verbatim text.
- `matn_ar`: a verbatim **substring** of the dataset Arabic text (heuristic isnad/matn split); never rewritten.
- `gradings.grade_class`: a deterministic bucket (sahih/hasan/daif/mawdu/unknown) of the grader's quoted label
  (see `app/core/grades.py`). The label and grader are shown verbatim.
- `gradings` rows with `source = collection_inclusion`: for Sahih al-Bukhari and Sahih Muslim, whose dataset
  has no per-hadith grading, we record "Sahih (included in Sahih al-Bukhari/Muslim)" attributed to the compiler.
