"""Hybrid (dense + reranker) and cross-lingual paths. Slow on CPU: run with RUN_SLOW=1 after build_index.py."""

import os

import pytest

from app.core import vectors
from app.core.retrieve import retrieve
from app.db import repo
from app.sources import dorar

pytestmark = pytest.mark.slow


@pytest.fixture(autouse=True)
def need_index(db_ready, monkeypatch):
    if os.environ.get("RUN_SLOW") != "1":
        pytest.skip("set RUN_SLOW=1 to run model-based tests")
    if not vectors.index_counts().get("hadith_ar"):
        pytest.skip("vector index not built")
    monkeypatch.setattr(dorar, "_default", dorar.DorarClient(offline=True))


def test_english_query_resolves_to_arabic_original():
    # English translation of a Bukhari hadith (dataset text) -> the Arabic hadith is retrieved with a high score
    row = repo.conn().execute("SELECT id, text_en FROM hadiths WHERE collection='bukhari' AND number='6018'").fetchone()
    en = row["text_en"].split(":", 1)[-1]
    res = retrieve(en, kind="hadith", lang="en", top_k=5)
    assert res.used_rerank and row["id"] in [c.id for c in res.candidates]


def test_cross_lingual_dorar_for_english_claim():
    if repo.cache_get("search:اطلبوا العلم ولو بالصين") is None or not vectors.index_counts().get("dorar_ar"):
        pytest.skip("Dorar seed cache / dorar_ar index not present")
    from app.core.pipeline import verify

    c = verify("The Prophet ﷺ said: Seek knowledge even if you have to go as far as China").claims[0]
    assert c.status == "red" and c.match_type == "paraphrase"
    assert "matched_via_dorar_cross_lingual" in c.notes and c.source.provider == "dorar.net"
