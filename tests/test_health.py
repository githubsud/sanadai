from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_components():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in {"ok", "degraded"}
    for key in ("db", "index", "dorar", "llm"):
        assert key in body


def test_index_page_served():
    r = client.get("/")
    assert r.status_code == 200
    assert "سند" in r.text
