"""Prepare-for-publishing + verbatim validator (texts from the DB; synthetic claims otherwise)."""

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.core import pipeline
from app.core.matn import find_excerpt
from app.core.prepare import Segment, decide, prepare, validate
from app.db import repo
from app.llm import provider as prov
from app.main import app
from app.sources import dorar


class NoLLM:
    name, available = "none", False

    def json(self, *a, **k):
        raise prov.LLMError("off")


@pytest.fixture(autouse=True)
def offline(db_ready, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "use_dense", False)
    monkeypatch.setattr(s, "use_reranker", False)
    monkeypatch.setattr(dorar, "_default", dorar.DorarClient(offline=True))
    prov.set_provider(NoLLM())
    yield
    prov.set_provider(None)


def claims_for(post):
    r = pipeline.verify(post)
    return r, [c.model_dump() for c in r.claims]


def test_quran_kept_verbatim_uthmani_with_citation():
    clean = " ".join(repo.get_ayah(112, a)["text_clean"] for a in (1, 2))
    post = f"قال تعالى: ﴿{clean}﴾ فتأملوا"
    _, claims = claims_for(post)
    p = prepare(post, claims, "ar")
    assert p.validated, p.validation_errors
    for a in (1, 2):
        assert repo.get_ayah(112, a)["text_uthmani"] in p.text
    assert "[1]" in p.text and "tanzil.net" in p.text and p.text.startswith("قال تعالى:")
    assert "فتأملوا" in p.text  # the user's own words are kept


def test_partial_hadith_replaced_by_verbatim_excerpt():
    row = repo.conn().execute("SELECT matn_ar FROM hadiths WHERE collection='bukhari' AND number='6138'").fetchone()
    excerpt = find_excerpt(row["matn_ar"], "من كان يومن بالله واليوم الاخر فليكرم ضيفه".split())
    assert excerpt and excerpt in row["matn_ar"]
    post = "قال النبي ﷺ: «من كان يؤمن بالله واليوم الآخر فليكرم ضيفه»"
    _, claims = claims_for(post)
    p = prepare(post, claims, "ar")
    assert p.validated and f"«{excerpt}»" in p.text and "sunnah.com/bukhari:6138" in p.text


def test_english_output_adds_dataset_translation():
    clean = repo.get_ayah(112, 1)["text_clean"]
    _, claims = claims_for(f"﴿{clean}﴾")
    p = prepare(f"﴿{clean}﴾", claims, "en")
    assert p.validated and repo.get_ayah(112, 1)["text_en"] in p.text and "Sources:" in p.text


def test_not_found_without_alternative_is_removed_with_its_cue():
    post = "مقدمة. قال رسول الله ﷺ: «نص تجريبي غير موجود في المصادر للاختبار» خاتمة."
    _, claims = claims_for(post)
    assert decide(claims[0]) in ("remove", "replace")
    p = prepare(post, claims, "ar")
    assert "نص تجريبي غير موجود" not in p.text
    if decide(claims[0]) == "remove":
        assert "قال رسول الله" not in p.text and "مقدمة." in p.text and "خاتمة." in p.text
        assert "حُذف" in p.text


def test_fabricated_replaced_by_alternative_from_cache():
    if repo.cache_get("search:اطلبوا العلم ولو بالصين") is None:
        pytest.skip("Dorar seed cache not present")
    post = "قال رسول الله ﷺ: «اطلبوا العلم ولو بالصين»"
    _, claims = claims_for(post)
    p = prepare(post, claims, "ar")
    assert "بالصين" not in p.text and p.validated
    assert claims[0]["alternatives"][0]["text_ar"] in p.text


def test_validator_rejects_non_verbatim_text():
    ayah = repo.get_ayah(112, 1)["text_uthmani"]
    from app.core.prepare import Prepared
    tampered = Prepared(text="x", sources=[], replacements=[], segments=[Segment(ayah + "ـ", "ayah")])
    assert not validate(tampered).validated
    missing = Prepared(text="nothing here", sources=[], replacements=[], segments=[Segment(ayah, "ayah")])
    assert validate(missing).validation_errors  # verbatim in DB but not present in the output
    fake_hadith = Prepared(text="«نص مختلق»", sources=[], replacements=[], segments=[Segment("نص مختلق", "hadith")])
    assert not validate(fake_hadith).validated


def test_api_prepare_roundtrip_and_expired():
    client = TestClient(app)
    clean = repo.get_ayah(112, 3)["text_clean"]
    v = client.post("/api/verify", json={"text": f"﴿{clean}﴾"}).json()
    r = client.post("/api/prepare", json={"check_id": v["check_id"], "output_lang": "ar"})
    assert r.status_code == 200 and r.json()["validated"]
    assert repo.get_ayah(112, 3)["text_uthmani"] in r.json()["text"]
    assert client.post("/api/prepare", json={"check_id": "nope"}).status_code == 404
