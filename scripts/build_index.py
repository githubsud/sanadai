"""Build the Chroma vector index from db/sanad.db with BAAI/bge-m3.

Collections (IDs = SQLite ids as strings):
  ayah_ar     normalized simple-clean ayah text
  ayah_en     Saheeh International translation
  hadith_ar   normalized matn (fallback: full text)
  hadith_en   English hadith text

Resumable: already-indexed IDs are skipped, so the script can be interrupted and re-run.
DEMO_SUBSET=true (default, see .env) indexes only the core collections for fast laptop setup.
"""

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.core import models  # noqa: E402
from app.core.vectors import COLLECTION_NAMES, DEMO_HADITH_COLLECTIONS, get_collection  # noqa: E402
from app.db import repo  # noqa: E402


def dorar_rows() -> list[tuple[str, str]]:
    """Distinct texts from cached Dorar search responses -> dorar_texts table (normalized text is embedded)."""
    import hashlib
    import json

    from app.core.normalize import normalize_ar

    c = repo.conn()
    seen: dict[str, tuple[str | None, str]] = {}
    for (js,) in c.execute("SELECT response_json FROM dorar_cache WHERE endpoint = 'search'"):
        for h in json.loads(js):
            t = (h.get("text") or "").strip()
            if t:
                seen.setdefault(hashlib.sha1(t.encode()).hexdigest()[:20], (h.get("hadith_id"), t))
    c.executemany("INSERT OR IGNORE INTO dorar_texts (key, hadith_id, text) VALUES (?,?,?)",
                  [(k, hid, t) for k, (hid, t) in seen.items()])
    c.commit()
    return [(k, normalize_ar(t)) for k, (_hid, t) in seen.items()]


def rows_for(name: str, demo: bool, collections: list[str] | None) -> list[tuple[str, str]]:
    c = repo.conn()
    if name == "dorar_ar":
        return dorar_rows()
    if name == "ayah_ar":
        sql, args = "SELECT id, text_norm FROM ayahs ORDER BY id", []
    elif name == "ayah_en":
        sql, args = "SELECT id, text_en FROM ayahs WHERE text_en IS NOT NULL ORDER BY id", []
    else:
        cols = collections or (DEMO_HADITH_COLLECTIONS if demo else None)
        field = "coalesce(matn_norm, text_norm)" if name == "hadith_ar" else "text_en"
        sql = f"SELECT id, {field} FROM hadiths WHERE {field} IS NOT NULL"
        args: list = []
        if cols:
            sql += f" AND collection IN ({','.join('?' * len(cols))})"
            args = list(cols)
        sql += " ORDER BY id"
    return [(str(i), t) for i, t in c.execute(sql, args) if t and t.strip()]


def index(name: str, demo: bool, collections: list[str] | None, batch: int, limit: int | None) -> None:
    col = get_collection(name)
    rows = rows_for(name, demo, collections)
    if limit:
        rows = rows[:limit]
    existing: set[str] = set()
    for i in range(0, len(rows), 5000):
        ids = [r[0] for r in rows[i:i + 5000]]
        existing.update(col.get(ids=ids, include=[])["ids"])
    todo = [r for r in rows if r[0] not in existing]
    print(f"[{name}] {len(rows)} docs, {len(existing)} already indexed, {len(todo)} to embed", flush=True)
    t0 = time.time()
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        vecs = models.embed([t for _, t in chunk])
        col.upsert(ids=[k for k, _ in chunk], embeddings=vecs)
        done = i + len(chunk)
        if done % (batch * 8) == 0 or done == len(todo):
            rate = done / max(time.time() - t0, 1e-6)
            eta = (len(todo) - done) / max(rate, 1e-6)
            print(f"  {done}/{len(todo)}  {rate:.1f} docs/s  eta {eta / 60:.1f} min", flush=True)


def main() -> int:
    s = get_settings()
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="index all hadith collections (ignores DEMO_SUBSET)")
    ap.add_argument("--only", nargs="*", choices=COLLECTION_NAMES, help="index only these vector collections")
    ap.add_argument("--collections", nargs="*", help="hadith collections to index (e.g. bukhari muslim)")
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--limit", type=int, help="debug: max docs per vector collection")
    args = ap.parse_args()
    demo = s.demo_subset and not args.full
    print(f"models={models.describe()} demo_subset={demo} chroma={s.resolve(s.chroma_path)}")
    # hadith_en is slow on CPU; in demo mode English queries use English FTS + cross-lingual dense on hadith_ar.
    names = args.only or [n for n in COLLECTION_NAMES if not (demo and n == "hadith_en")]
    for name in names:
        index(name, demo, args.collections, args.batch, args.limit)
    print("done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
