"""SanadAI FastAPI application."""

import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import health, lookup
from app.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title="SanadAI — سند AI",
    description="Verify Quran verses, hadith and attributed sayings against trusted sources. "
    "The system quotes sources and gradings; it never issues religious rulings.",
    version="0.1.0",
)

app.include_router(health.router)
app.include_router(lookup.router)

# Static frontend last so /api/* routes take precedence.
app.mount("/", StaticFiles(directory=get_settings().web_dir, html=True), name="web")
