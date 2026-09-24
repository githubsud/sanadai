"""Health, eval, error handling and security headers."""

import json

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_health_reports_components(db_ready, monkeypatch):
    monkeypatch.setattr(get_settings(), "dorar_offline", True)
    body = client.get("/api/health").json()
    assert body["db"]["ok"] and body["db"]["counts"]["ayahs"] == 6236
    assert body["dorar"] == {"reachable": False, "offline_mode": True, "detail": "offline mode: cached results only"}
    assert "configured" in body["llm"]


def test_eval_latest(tmp_path, monkeypatch):
    p = tmp_path / "results.json"
    monkeypatch.setattr(get_settings(), "eval_results_path", p)
    assert client.get("/api/eval/latest").status_code == 404
    p.write_text(json.dumps({"metrics": {"n": 1}}), encoding="utf-8")
    assert client.get("/api/eval/latest").json()["metrics"]["n"] == 1


def test_security_headers_and_openapi():
    r = client.get("/api/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert client.get("/openapi.json").json()["info"]["title"].startswith("SanadAI")


def test_unhandled_error_is_json_500(monkeypatch):
    from app.core import pipeline

    def boom(*a, **k):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(pipeline, "verify", boom)
    r = client.post("/api/verify", json={"text": "نص تجريبي"})
    assert r.status_code == 500 and "secret" not in r.text


def test_lookup_404s(db_ready):
    assert client.get("/api/hadith/99999999").status_code == 404
    assert client.get("/api/ayah/1/99").status_code == 404
