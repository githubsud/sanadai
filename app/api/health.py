import sqlite3

from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(prefix="/api", tags=["health"])


def _db_status() -> dict:
    s = get_settings()
    path = s.resolve(s.db_path)
    if not path.exists():
        return {"ok": False, "detail": "database not built (run scripts/build_db.py)"}
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as con:
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                      for t in ("ayahs", "hadiths", "gradings") if t in tables}
        return {"ok": bool(counts.get("ayahs")) and bool(counts.get("hadiths")), "counts": counts}
    except sqlite3.Error as e:
        return {"ok": False, "detail": str(e)}


def _index_status() -> dict:
    s = get_settings()
    path = s.resolve(s.chroma_path)
    ok = path.exists() and any(path.iterdir())
    return {"ok": ok, "detail": None if ok else "vector index not built (run scripts/build_index.py)"}


@router.get("/health")
async def health() -> dict:
    s = get_settings()
    db = _db_status()
    index = _index_status()
    return {
        "status": "ok" if db["ok"] else "degraded",
        "db": db,
        "index": index,
        "dorar": {"offline_mode": s.dorar_offline},
        "llm": {"configured": s.llm_configured, "model": s.llm_model},
    }
