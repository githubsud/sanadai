"""Build db/sanad.db from data/raw/ (run scripts/download_data.py first).

Tables: ayahs (Tanzil), hadiths + gradings (fawazahmed0/hadith-api), FTS5 indexes.
Rebuilds content tables from scratch; keeps dorar_cache and checks.
"""

import json
import re
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.core.grades import classify_label_en, label_to_ar  # noqa: E402
from app.core.matn import extract_matn  # noqa: E402
from app.core.normalize import normalize_ar, normalize_en  # noqa: E402

RAW = ROOT / "data" / "raw"
SCHEMA = ROOT / "app" / "db" / "schema.sql"

# collection key -> (display name ar, display name en, sunnah.com slug)
COLLECTIONS = {
    "bukhari": ("صحيح البخاري", "Sahih al-Bukhari", "bukhari"),
    "muslim": ("صحيح مسلم", "Sahih Muslim", "muslim"),
    "abudawud": ("سنن أبي داود", "Sunan Abi Dawud", "abudawud"),
    "tirmidhi": ("جامع الترمذي", "Jami` at-Tirmidhi", "tirmidhi"),
    "nasai": ("سنن النسائي", "Sunan an-Nasa'i", "nasai"),
    "ibnmajah": ("سنن ابن ماجه", "Sunan Ibn Majah", "ibnmajah"),
    "malik": ("موطأ مالك", "Muwatta Malik", "malik"),
    "nawawi": ("الأربعون النووية", "40 Hadith an-Nawawi", "nawawi40"),
    "qudsi": ("الأحاديث القدسية الأربعون", "40 Hadith Qudsi", "qudsi40"),
    "dehlawi": ("أربعون الدهلوي", "40 Hadith Shah Waliullah", "shahwaliullah40"),
}

# Collections whose every hadith is authentic by the compiler's stated condition. We record this as an
# explicit, attributed grading ("included in the Sahih") rather than inventing a per-hadith verdict.
SAHIH_BY_INCLUSION = {
    "bukhari": ("صحيح (أخرجه البخاري في صحيحه)", "Sahih (included in Sahih al-Bukhari)", "البخاري"),
    "muslim": ("صحيح (أخرجه مسلم في صحيحه)", "Sahih (included in Sahih Muslim)", "مسلم"),
}

_NARRATED = re.compile(r"^\s*(?:Narrated|It was narrated from|It was narrated that)\s+([^:]{2,80}?)\s*:", re.I)


def read_tanzil(path: Path) -> dict[tuple[int, int], str]:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        s, a, text = line.split("|", 2)
        out[(int(s), int(a))] = text
    return out


def read_tanzil_xml(path: Path) -> tuple[dict[tuple[int, int], str], dict[tuple[int, int], str]]:
    """(texts, bismillahs) keyed by (surah, ayah) — attribute values are Tanzil's text, verbatim."""
    texts, bism = {}, {}
    for sura in ET.parse(path).getroot().iter("sura"):
        for aya in sura.iter("aya"):
            key = (int(sura.get("index")), int(aya.get("index")))
            texts[key] = aya.get("text")
            if aya.get("bismillah"):
                bism[key] = aya.get("bismillah")
    return texts, bism


def build_ayahs(con: sqlite3.Connection) -> int:
    uth, bism = read_tanzil_xml(RAW / "tanzil" / "quran-uthmani.xml")
    clean, _ = read_tanzil_xml(RAW / "tanzil" / "quran-simple-clean.xml")
    en_path = RAW / "tanzil" / "en.sahih.txt"
    en = read_tanzil(en_path) if en_path.exists() else {}
    meta = ET.parse(RAW / "tanzil" / "quran-data.xml").getroot()
    names = {int(s.get("index")): (s.get("name"), s.get("tname")) for s in meta.iter("sura")}
    assert len(uth) == len(clean) == 6236, f"unexpected ayah counts {len(uth)} {len(clean)}"
    rows = []
    for gid, key in enumerate(sorted(uth), start=1):
        s, a = key
        rows.append((gid, s, a, names[s][0], names[s][1], uth[key], clean[key],
                     normalize_ar(clean[key], honorifics=False), en.get(key), bism.get(key)))
    con.executemany("INSERT INTO ayahs VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    return len(rows)


def _number(h: dict) -> str:
    n = h.get("arabicnumber") or h.get("hadithnumber")
    if isinstance(n, float) and n.is_integer():
        n = int(n)
    return str(n)


def build_hadiths(con: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    now_src = "fawazahmed0/hadith-api@1"
    for col, (_name_ar, _name_en, slug) in COLLECTIONS.items():
        ara = json.loads((RAW / "hadith-api" / f"ara-{col}.json").read_text(encoding="utf-8"))
        eng_path = RAW / "hadith-api" / f"eng-{col}.json"
        eng = json.loads(eng_path.read_text(encoding="utf-8")) if eng_path.exists() else {"hadiths": []}
        sections = ara.get("metadata", {}).get("sections") or ara.get("metadata", {}).get("section") or {}
        en_by_num = {h["hadithnumber"]: h for h in eng["hadiths"]}
        seen: set[str] = set()
        n = 0
        for h in ara["hadiths"]:
            text_ar = (h.get("text") or "").strip()
            if not text_ar:
                continue
            number = _number(h)
            if number in seen:  # item without arabicnumber colliding with another's number: use in-book no.
                number = f"{h['hadithnumber']}-inbook"
            if number in seen:
                continue
            seen.add(number)
            en_h = en_by_num.get(h["hadithnumber"], {})
            text_en = (en_h.get("text") or "").strip() or None
            book_no = str((h.get("reference") or {}).get("book", ""))
            book = sections.get(book_no) or None
            matn = extract_matn(text_ar)
            narrator = None
            if text_en and (m := _NARRATED.match(text_en)):
                narrator = m.group(1).strip()
            cur = con.execute(
                "INSERT INTO hadiths (collection, book, number, text_ar, matn_ar, text_norm, matn_norm, "
                "text_en, text_en_norm, narrator, source_url, source_dataset) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (col, book, number, text_ar, matn, normalize_ar(text_ar),
                 normalize_ar(matn) if matn else None, text_en,
                 normalize_en(text_en) if text_en else None, narrator,
                 f"https://sunnah.com/{slug}:{number.split('.')[0].split('-')[0]}", now_src),
            )
            hid = cur.lastrowid
            for g in h.get("grades") or []:
                label = (g.get("grade") or "").strip()
                if not label or label == "-":
                    continue
                con.execute(
                    "INSERT INTO gradings (hadith_id, grade_ar, grade_en, grade_class, grader, reference, source) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (hid, label_to_ar(label), label, classify_label_en(label), g.get("name") or "unknown",
                     f"{COLLECTIONS[col][1]} {number}", now_src),
                )
            if col in SAHIH_BY_INCLUSION:
                g_ar, g_en, grader = SAHIH_BY_INCLUSION[col]
                con.execute(
                    "INSERT INTO gradings (hadith_id, grade_ar, grade_en, grade_class, grader, reference, source) "
                    "VALUES (?,?,?,'sahih',?,?,?)",
                    (hid, g_ar, g_en, grader, f"{COLLECTIONS[col][1]} {number}", "collection_inclusion"),
                )
            n += 1
        counts[col] = n
    return counts


def main() -> int:
    s = get_settings()
    db_path = s.resolve(s.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    con = sqlite3.connect(db_path)
    con.executescript("DROP TABLE IF EXISTS hadiths_fts; DROP TABLE IF EXISTS hadiths_en_fts; "
                      "DROP TABLE IF EXISTS ayahs_en_fts; "
                      "DROP TABLE IF EXISTS ayahs_fts; DROP TABLE IF EXISTS gradings; "
                      "DROP TABLE IF EXISTS hadiths; DROP TABLE IF EXISTS ayahs;")
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    with con:
        n_ayahs = build_ayahs(con)
        counts = build_hadiths(con)
        con.execute("INSERT INTO hadiths_fts(hadiths_fts) VALUES ('rebuild')")
        con.execute("INSERT INTO hadiths_en_fts(hadiths_en_fts) VALUES ('rebuild')")
        con.execute("INSERT INTO ayahs_fts(ayahs_fts) VALUES ('rebuild')")
        con.execute("INSERT INTO ayahs_en_fts(ayahs_en_fts) VALUES ('rebuild')")
        con.execute("INSERT OR REPLACE INTO meta VALUES ('built_at', ?)", (datetime.now(UTC).isoformat(),))
    con.execute("VACUUM")

    print(f"ayahs: {n_ayahs}")
    print("hadiths per collection:")
    for col, n in counts.items():
        print(f"  {col:<10} {n:>6}")
    print(f"  {'TOTAL':<10} {sum(counts.values()):>6}")
    for cls, n in con.execute("SELECT grade_class, COUNT(*) FROM gradings GROUP BY 1 ORDER BY 2 DESC"):
        print(f"gradings[{cls}] = {n}")
    matn_cov = con.execute("SELECT AVG(matn_ar IS NOT NULL) FROM hadiths").fetchone()[0]
    print(f"matn extracted for {matn_cov:.1%} of hadiths")
    print(f"built {db_path} in {time.time() - t0:.1f}s")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
