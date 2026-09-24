"""Read access to sanad.db. All sacred texts and gradings returned by the app come through here."""

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

from app.config import get_settings

_local = threading.local()

HADITH_COLS = ("id, collection, book, number, text_ar, matn_ar, text_norm, matn_norm, text_en, narrator, "
               "source_url, source_dataset")
AYAH_COLS = "id, surah, ayah, surah_name_ar, surah_name_en, text_uthmani, text_clean, text_norm, text_en"

COLLECTION_NAMES = {
    "bukhari": ("صحيح البخاري", "Sahih al-Bukhari"),
    "muslim": ("صحيح مسلم", "Sahih Muslim"),
    "abudawud": ("سنن أبي داود", "Sunan Abi Dawud"),
    "tirmidhi": ("جامع الترمذي", "Jami` at-Tirmidhi"),
    "nasai": ("سنن النسائي", "Sunan an-Nasa'i"),
    "ibnmajah": ("سنن ابن ماجه", "Sunan Ibn Majah"),
    "malik": ("موطأ مالك", "Muwatta Malik"),
    "nawawi": ("الأربعون النووية", "40 Hadith an-Nawawi"),
    "qudsi": ("الأحاديث القدسية الأربعون", "40 Hadith Qudsi"),
    "dehlawi": ("أربعون الدهلوي", "40 Hadith Shah Waliullah"),
}


def db_path() -> Path:
    s = get_settings()
    return s.resolve(s.db_path)


def conn() -> sqlite3.Connection:
    """One connection per thread (sqlite3 objects are not thread-safe)."""
    c = getattr(_local, "con", None)
    if c is None:
        c = sqlite3.connect(db_path(), check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys = ON")
        _local.con = c
    return c


def _fts_query(text_norm: str, max_terms: int = 40) -> str:
    """OR-query of unique quoted tokens (recall-oriented; BM25 does the ranking)."""
    seen: list[str] = []
    for t in text_norm.split():
        t = t.replace('"', "")
        if t and t not in seen:
            seen.append(t)
    return " OR ".join(f'"{t}"' for t in seen[:max_terms])


# ---------- hadith ----------

def get_hadith(hid: int) -> dict | None:
    row = conn().execute(f"SELECT {HADITH_COLS} FROM hadiths WHERE id = ?", (hid,)).fetchone()
    if not row:
        return None
    h = dict(row)
    h["collection_name_ar"], h["collection_name_en"] = COLLECTION_NAMES.get(h["collection"], (h["collection"],) * 2)
    h["gradings"] = get_gradings(hid)
    return h


def get_hadiths(ids: list[int]) -> dict[int, dict]:
    return {i: h for i in ids if (h := get_hadith(i))}


def get_gradings(hid: int) -> list[dict]:
    rows = conn().execute(
        "SELECT grade_ar, grade_en, grade_class, grader, reference, source FROM gradings WHERE hadith_id = ? "
        "ORDER BY id", (hid,)).fetchall()
    return [dict(r) for r in rows]


def fts_hadiths(text_norm: str, limit: int = 50, lang: str = "ar",
                collections: list[str] | None = None) -> list[tuple[int, float]]:
    """BM25 search. Returns [(hadith_id, bm25)] best first (bm25 is negative; lower is better)."""
    q = _fts_query(text_norm)
    if not q:
        return []
    table = "hadiths_fts" if lang == "ar" else "hadiths_en_fts"
    sql = f"SELECT rowid, bm25({table}) FROM {table} WHERE {table} MATCH ?"
    args: list = [q]
    if collections:
        sql += f" AND rowid IN (SELECT id FROM hadiths WHERE collection IN ({','.join('?' * len(collections))}))"
        args += collections
    sql += " ORDER BY bm25(" + table + ") LIMIT ?"
    args.append(limit)
    return [(r[0], r[1]) for r in conn().execute(sql, args).fetchall()]


# ---------- quran ----------

def get_ayah(surah: int, ayah: int) -> dict | None:
    row = conn().execute(f"SELECT {AYAH_COLS} FROM ayahs WHERE surah = ? AND ayah = ?", (surah, ayah)).fetchone()
    return dict(row) if row else None


def get_ayah_by_id(aid: int) -> dict | None:
    row = conn().execute(f"SELECT {AYAH_COLS} FROM ayahs WHERE id = ?", (aid,)).fetchone()
    return dict(row) if row else None


def get_ayah_range(start_id: int, end_id: int) -> list[dict]:
    rows = conn().execute(f"SELECT {AYAH_COLS} FROM ayahs WHERE id BETWEEN ? AND ? ORDER BY id",
                          (start_id, end_id)).fetchall()
    return [dict(r) for r in rows]


def all_ayahs_norm() -> list[tuple[int, int, int, str]]:
    """[(id, surah, ayah, text_norm)] in mushaf order — for exact / sliding-window matching."""
    return [tuple(r) for r in conn().execute("SELECT id, surah, ayah, text_norm FROM ayahs ORDER BY id")]


def fts_ayahs(text_norm: str, limit: int = 50) -> list[tuple[int, float]]:
    q = _fts_query(text_norm)
    if not q:
        return []
    return [(r[0], r[1]) for r in conn().execute(
        "SELECT rowid, bm25(ayahs_fts) FROM ayahs_fts WHERE ayahs_fts MATCH ? ORDER BY bm25(ayahs_fts) LIMIT ?",
        (q, limit)).fetchall()]


# ---------- dorar cache & checks ----------

def cache_get(key: str) -> dict | list | None:
    row = conn().execute("SELECT response_json FROM dorar_cache WHERE key = ?", (key,)).fetchone()
    return json.loads(row[0]) if row else None


def cache_put(key: str, endpoint: str, response: dict | list) -> None:
    c = conn()
    c.execute("INSERT OR REPLACE INTO dorar_cache (key, endpoint, response_json, fetched_at) VALUES (?,?,?,?)",
              (key, endpoint, json.dumps(response, ensure_ascii=False), datetime.now(UTC).isoformat()))
    c.commit()


def save_check(check_id: str, input_hash: str, result: dict) -> None:
    c = conn()
    c.execute("INSERT OR REPLACE INTO checks (id, created_at, input_hash, result_json) VALUES (?,?,?,?)",
              (check_id, datetime.now(UTC).isoformat(), input_hash, json.dumps(result, ensure_ascii=False)))
    c.commit()


def get_check(check_id: str) -> dict | None:
    row = conn().execute("SELECT result_json FROM checks WHERE id = ?", (check_id,)).fetchone()
    return json.loads(row[0]) if row else None


def text_exists_verbatim(text: str) -> bool:
    """True if `text` appears verbatim inside any stored ayah (uthmani/clean) or hadith Arabic/English text."""
    if not text:
        return False
    c = conn()
    for sql in ("SELECT 1 FROM ayahs WHERE instr(text_uthmani, ?) > 0 OR instr(text_clean, ?) > 0 LIMIT 1",
                "SELECT 1 FROM hadiths WHERE instr(text_ar, ?) > 0 OR instr(text_en, ?) > 0 LIMIT 1"):
        if c.execute(sql, (text, text)).fetchone():
            return True
    return False
