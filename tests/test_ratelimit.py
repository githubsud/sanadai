"""Public-deployment rate limits."""

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.core import extract, ratelimit
from app.core.ratelimit import SlidingWindow
from app.llm import provider as prov
from app.main import app


@pytest.fixture(autouse=True)
def fresh_limits():
    ratelimit.reset()
    yield
    ratelimit.reset()


def test_sliding_window():
    w = SlidingWindow(2, 3600)
    assert w.allow("a") and w.allow("a") and not w.allow("a")
    assert w.allow("b")  # per key
    assert SlidingWindow(0, 3600).allow("x")  # 0 disables


def test_llm_budget_per_visitor_and_global(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "rate_llm_per_hour", 2)
    monkeypatch.setattr(s, "rate_llm_per_day_global", 3)
    assert ratelimit.allow_llm("ip1") and ratelimit.allow_llm("ip1") and not ratelimit.allow_llm("ip1")
    assert ratelimit.allow_llm("ip2")          # 3rd global call
    assert not ratelimit.allow_llm("ip3")      # global daily cap reached


def test_verify_limit_returns_429(db_ready, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "rate_verify_per_hour", 1)
    monkeypatch.setattr(s, "use_dense", False)
    monkeypatch.setattr(s, "use_reranker", False)
    client = TestClient(app)
    body = {"text": "﴿قل هو الله أحد﴾"}
    hdr = {"X-Forwarded-For": "203.0.113.7"}  # documentation IP range
    assert client.post("/api/verify", json=body, headers=hdr).status_code == 200
    assert client.post("/api/verify", json=body, headers=hdr).status_code == 429
    assert client.post("/api/verify", json=body, headers={"X-Forwarded-For": "203.0.113.8"}).status_code == 200


class CountingLLM:
    name, available, calls = "fake", True, 0

    def json(self, *a, **k):
        CountingLLM.calls += 1
        raise prov.LLMError("should not be called")


def test_llm_not_called_when_over_budget():
    prov.set_provider(CountingLLM())
    try:
        ex = extract.extract_claims("قال رسول الله ﷺ: «نص تجريبي للاختبار»", allow_llm=False)
        assert CountingLLM.calls == 0 and ex.method == "rules" and "llm_rate_limited" in ex.notes
    finally:
        prov.set_provider(None)
