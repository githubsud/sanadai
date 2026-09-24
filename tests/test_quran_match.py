"""Quran matching against the real Tanzil DB (texts are read from the DB, never hardcoded).

Runs lexical-only (no dense index / reranker) so it is fast and deterministic.
"""

import pytest

from app.config import get_settings
from app.core.normalize import normalize_ar
from app.core.quran_match import exact_matches, match_quran
from app.db import repo


@pytest.fixture(autouse=True)
def lexical_only(db_ready, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "use_dense", False)
    monkeypatch.setattr(s, "use_reranker", False)


def clean(s, a):
    return repo.get_ayah(s, a)["text_clean"]


def test_exact_single_ayah():
    m = match_quran(clean(112, 1))
    assert m.match_type == "identical" and m.ref()["ref"] == "112:1"
    assert m.ref()["surah_name_ar"] == "الإخلاص"


def test_exact_multi_ayah_range():
    text = " ".join(clean(112, a) for a in range(1, 5))
    m = match_quran(text)
    assert m.match_type == "identical" and m.ref()["ref"] == "112:1-4"


def test_display_text_is_verbatim_uthmani():
    m = match_quran(clean(112, 1))
    assert m.ref()["text_uthmani"] == repo.get_ayah(112, 1)["text_uthmani"]


def test_partial_excerpt_of_long_ayah():
    words = clean(2, 255).split()
    excerpt = " ".join(words[10:22])
    m = match_quran(excerpt)
    assert m.match_type == "partial" and m.ref()["ref"] == "2:255"


def test_uthmani_input_is_recognised():
    m = match_quran(repo.get_ayah(1, 2)["text_uthmani"])
    assert m.match_type == "identical" and m.ref()["ref"] == "1:2"


def test_with_diacritics_and_punctuation():
    m = match_quran("«" + repo.get_ayah(112, 2)["text_uthmani"] + "»!")
    assert m.match_type == "identical" and m.ref()["ref"] == "112:2"


def test_repeated_verse_reports_occurrences():
    # 3:2 is identical to the opening of 2:255: the whole-ayah occurrence (3:2) wins, 2:255 listed as occurrence
    text = clean(3, 2)
    hits = exact_matches(repo.get_ayah(3, 2)["text_norm"])
    assert len(hits) >= 2
    m = match_quran(text)
    assert m.ref()["ref"] == "3:2" and m.match_type == "identical"
    assert any(repo.get_ayah_by_id(a0)["surah"] == 2 for a0, _ in m.occurrences)


def test_deliberately_altered_word_detected():
    # Synthetic alteration for testing: swap one word of 2:255's first sentence with a different word.
    words = clean(2, 255).split()[:12]
    original = words[8]
    words[8] = "غفله"
    m = match_quran(" ".join(words))
    assert m is not None and m.ref()["ref"] == "2:255"
    assert m.match_type == "altered"
    rep = [d for d in m.classification.diff if d["op"] == "replace"]
    assert rep and rep[0]["text"] == "غفله" and rep[0]["source"] == normalize_ar(original, honorifics=False)


def test_unrelated_text_not_identical():
    m = match_quran("هذه جملة تجريبية لا توجد في القران اصلا ابدا")
    assert m is None or m.match_type in ("not_found", "altered")
