"""End-to-end pipeline + /api/verify, offline and deterministic (lexical-only, Dorar from cache, fake LLM).
Sacred texts are read from the DB at test time; synthetic placeholder text is used for non-religious input."""

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.core import extract, pipeline
from app.db import repo
from app.llm import provider as prov
from app.llm.provider import LLMError
from app.main import app
from app.sources import dorar


@pytest.fixture(autouse=True)
def offline_fast(db_ready, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "use_dense", False)
    monkeypatch.setattr(s, "use_reranker", False)
    monkeypatch.setattr(dorar, "_default", dorar.DorarClient(offline=True))
    prov.set_provider(NoLLM())
    yield
    prov.set_provider(None)


class NoLLM:
    name = "none"
    available = False

    def json(self, *a, **k):
        raise LLMError("not configured")


class FakeLLM:
    name = "fake"
    available = True

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def json(self, system, content, schema, max_tokens=4096):
        self.calls += 1
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def bukhari_matn(offset=200):
    return repo.conn().execute(
        "SELECT id, matn_ar FROM hadiths WHERE collection='bukhari' AND matn_ar IS NOT NULL AND length(matn_ar) "
        "BETWEEN 60 AND 200 ORDER BY id LIMIT 1 OFFSET ?", (offset,)).fetchone()


def test_quran_verse_green():
    verse = repo.get_ayah(112, 1)["text_clean"]
    r = pipeline.verify(f"قال تعالى: ﴿{verse}﴾")
    c = r.claims[0]
    assert (c.claim_type, c.status, c.match_type) == ("quran", "green", "identical")
    assert c.ayah.ref == "112:1" and c.ayah.text_uthmani == repo.get_ayah(112, 1)["text_uthmani"]
    assert c.sanad_score == 100


def test_bukhari_hadith_green_with_evidence():
    row = bukhari_matn()
    r = pipeline.verify(f"قال رسول الله ﷺ: «{row['matn_ar']}»")
    c = r.claims[0]
    assert c.status == "green" and c.match_type in ("identical", "partial")
    assert c.source.hadith_id == row["id"] and c.source.provider.startswith("fawazahmed0")
    assert any(g.source == "collection_inclusion" for g in c.gradings)
    assert [s.step for s in c.evidence_trace][:3] == ["quran_match", "retrieve", "classify"]


def test_primary_collection_cited_over_secondary_compilation():
    # Riyad as-Salihin 26 reproduces Bukhari 6138's wording without diacritics: Bukhari must be cited
    r = pipeline.verify("قال النبي ﷺ: «من كان يؤمن بالله واليوم الآخر فليكرم ضيفه»")
    c = r.claims[0]
    assert c.source.collection_en == "Sahih al-Bukhari" and c.status == "green"


def test_altered_hadith_is_amber_with_diff():
    row = bukhari_matn(300)
    words = row["matn_ar"].split()
    words[len(words) // 2] = "كلمةمبدلةللاختبار"
    r = pipeline.verify("قال رسول الله ﷺ: «" + " ".join(words) + "»")
    c = r.claims[0]
    assert c.match_type == "altered" and c.status == "amber"
    assert any(d.op == "replace" and d.text == "كلمهمبدلهللاختبار" for d in c.diff)


def test_non_religious_text_is_not_red():
    r = pipeline.verify("هذه جملة تجريبية عن الطقس الجميل اليوم في المدينة")
    c = r.claims[0]
    assert c.claim_type == "saying" and c.match_type == "not_found" and c.status == "amber"
    assert c.source is None and c.gradings == []


def test_fabricated_from_dorar_cache_is_red():
    if repo.cache_get("search:" + "اطلبوا العلم ولو بالصين") is None:
        pytest.skip("Dorar seed cache not present (run scripts/seed_dorar.py)")
    r = pipeline.verify("قال رسول الله ﷺ: «اطلبوا العلم ولو بالصين»")
    c = r.claims[0]
    assert c.status == "red" and c.grade_class == "mawdu"
    assert any(g.source == "dorar.net" and g.grader for g in c.gradings)
    assert all(a.grade_class in ("sahih", "hasan") for a in c.alternatives)


def test_dorar_unreachable_degrades_gracefully():
    r = pipeline.verify("قال رسول الله ﷺ: «نص تجريبي غير موجود في اي مصدر للاختبار»")
    c = r.claims[0]
    assert c.status == "red" and c.match_type == "not_found"
    assert any(s.step == "dorar" and s.status == "degraded" for s in c.evidence_trace)


def test_check_persisted_without_input_text():
    r = pipeline.verify(f"﴿{repo.get_ayah(112, 2)['text_clean']}﴾")
    stored = repo.get_check(r.check_id)
    assert stored and stored["input_text"] == ""
    assert pipeline.recall_post(r.check_id) is not None


# ---------------- LLM extraction guarantees (P1/P3) ----------------

def test_llm_claims_used_when_verbatim():
    verse = repo.get_ayah(112, 1)["text_clean"]
    post = f"تأمل قوله: {verse} صدق الله"
    fake = FakeLLM([{"claims": [{"text": verse, "claim_type": "quran", "attributed_to": None, "lang": "ar"}]}])
    prov.set_provider(fake)
    ex = extract.extract_claims(post)
    assert ex.method == "llm" and ex.claims[0].text == verse


def test_llm_non_verbatim_claim_is_dropped_and_rules_used():
    post = "قال رسول الله ﷺ: «نص تجريبي للاختبار»"
    invented = {"claims": [{"text": "نص لم يرد في المنشور اطلاقا", "claim_type": "hadith",
                            "attributed_to": None, "lang": "ar"}]}
    prov.set_provider(FakeLLM([invented, invented]))
    ex = extract.extract_claims(post)
    assert ex.method == "rules" and ex.claims[0].text == "نص تجريبي للاختبار"
    assert "llm_claims_not_verbatim" in ex.notes


def test_llm_invalid_json_retries_once_then_falls_back():
    fake = FakeLLM([{"claims": [{"text": "x"}]}, LLMError("boom")])
    prov.set_provider(fake)
    ex = extract.extract_claims("قال النبي ﷺ: «نص تجريبي للاختبار»")
    assert fake.calls == 2 and ex.method == "rules"


def test_find_verbatim_whitespace_insensitive():
    assert extract.find_verbatim("a  b\nc", "x a b c y") == "a b c"
    assert extract.find_verbatim("not there", "x a b c y") is None


# ---------------- API ----------------

def test_api_verify_and_validation():
    client = TestClient(app)
    r = client.post("/api/verify", json={"text": f"﴿{repo.get_ayah(1, 2)['text_clean']}﴾"})
    assert r.status_code == 200
    body = r.json()
    assert body["claims"][0]["status"] == "green" and body["claims"][0]["ayah"]["ref"] == "1:2"
    assert client.post("/api/verify", json={}).status_code == 422
    assert client.post("/api/verify", json={"text": "x" * 6000}).status_code == 422
    assert client.post("/api/verify", json={"image_base64": "!!!notbase64!!!"}).status_code == 422


def test_api_image_without_llm_is_degraded_not_crash():
    import base64
    png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode()
    r = TestClient(app).post("/api/verify", json={"image_base64": png})
    assert r.status_code == 200 and "ocr_unavailable" in r.json()["notes"]
