import sqlite3
import time

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool

from app.config import get_settings

router = APIRouter(prefix="/api", tags=["health"])

_DORAR_TTL_S = 300
_dorar_cache: dict = {"at": 0.0, "value": None}


def _db_status() -> dict:
    s = get_settings()
    path = s.resolve(s.db_path)
    if not path.exists():
        return {"ok": False, "detail": "database not built (run scripts/build_db.py)"}
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as con:
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                      for t in ("ayahs", "hadiths", "gradings", "dorar_cache") if t in tables}
        return {"ok": bool(counts.get("ayahs")) and bool(counts.get("hadiths")), "counts": counts}
    except sqlite3.Error as e:
        return {"ok": False, "detail": str(e)}


def _index_status() -> dict:
    s = get_settings()
    path = s.resolve(s.chroma_path)
    if not (path.exists() and any(path.iterdir())):
        return {"ok": False, "detail": "vector index not built (run scripts/build_index.py) — lexical search only"}
    from app.core import models, vectors

    counts = vectors.index_counts()
    return {"ok": any(counts.values()), "counts": counts, "models": models.describe()}


def _dorar_status() -> dict:
    s = get_settings()
    if s.dorar_offline:
        return {"reachable": False, "offline_mode": True, "detail": "offline mode: cached results only"}
    now = time.monotonic()
    if _dorar_cache["value"] is None or now - _dorar_cache["at"] > _DORAR_TTL_S:
        from app.sources.dorar import client

        _dorar_cache.update(at=now, value=client().reachable())
    return {"reachable": _dorar_cache["value"], "offline_mode": False}


def _llm_name() -> str:
    from app.llm.provider import get_provider

    p = get_provider()
    return f"{p.name}:{getattr(p, 'model', '')}" if p.available else "none (rule-based extraction)"


@router.get("/health")
async def health() -> dict:
    s = get_settings()
    db = _db_status()
    index, dorar = await run_in_threadpool(lambda: (_index_status(), _dorar_status()))
    return {
        "status": "ok" if db["ok"] else "degraded",
        "db": db,
        "index": index,
        "dorar": dorar,
        "llm": {"configured": s.llm_configured, "provider": _llm_name()},
    }
