"""SanadAI FastAPI application."""

import logging
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import eval as eval_api
from app.api import health, lookup, prepare, verify
from app.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("sanadai")


def _warm_up() -> None:
    """Load models and in-memory caches in the background so the first request is fast."""
    t0 = time.perf_counter()
    try:
        from app.core import quran_match, vectors
        from app.db import repo

        if not repo.db_path().exists():
            return
        quran_match._stream("clean")
        quran_match._stream("uthmani")
        s = get_settings()
        if s.use_dense and any(vectors.index_counts().values()):
            from app.core import models

            models.embed(["warm up"])
            if s.use_reranker:
                models.rerank("warm up", ["warm up"])
        log.info("warm-up done in %.1fs", time.perf_counter() - t0)
    except Exception as e:  # noqa: BLE001 - warm-up is best effort
        log.warning("warm-up skipped: %s", e)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if get_settings().warm_up:
        threading.Thread(target=_warm_up, name="warm-up", daemon=True).start()
    yield


app = FastAPI(
    title="SanadAI — سند AI",
    description="Verify Quran verses, hadith and attributed sayings against trusted sources. "
    "The system quotes sources and gradings; it never issues religious rulings.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def timing_and_headers(request: Request, call_next):
    t0 = time.perf_counter()
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        log.info("%s %s -> %s in %.0f ms", request.method, request.url.path, response.status_code,
                 (time.perf_counter() - t0) * 1000)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("unhandled error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "internal error — the request could not be completed"})


app.include_router(health.router)
app.include_router(lookup.router)
app.include_router(verify.router)
app.include_router(prepare.router)
app.include_router(eval_api.router)

# Static frontend last so /api/* routes take precedence.
app.mount("/", StaticFiles(directory=get_settings().web_dir, html=True), name="web")
