"""Dorar client: parsing (real trimmed responses saved in tests/fixtures), cache, offline mode, failures.
No network: an injected fetcher serves the fixtures; the cache is an in-memory dict."""

from pathlib import Path

import pytest

from app.sources import dorar
from app.sources.dorar import DorarClient, DorarUnavailable, FetchError, parse_h_page, parse_search

FIX = Path(__file__).parent / "fixtures"
SEARCH_HTML = (FIX / "dorar_search_sample.html").read_text(encoding="utf-8")
ALTS_HTML = (FIX / "dorar_alts_sample.html").read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def memory_cache(monkeypatch):
    store: dict = {}
    monkeypatch.setattr(dorar.repo, "cache_get", lambda k: store.get(k))
    monkeypatch.setattr(dorar.repo, "cache_put", lambda k, e, r: store.__setitem__(k, r))
    monkeypatch.setattr(dorar, "MIN_INTERVAL_S", 0.0)
    return store


def mock_client(handler, offline=False):
    return DorarClient(offline=offline, fetch=handler)


def serve(url: str, timeout: float) -> str:
    if "/hadith/search?" in url:
        return SEARCH_HTML
    if "/h/" in url and "alts=1" in url:
        return ALTS_HTML
    raise FetchError(404, "not found")


def test_parse_search_fields():
    hits = parse_search(SEARCH_HTML)
    assert len(hits) == 4
    h = hits[0]
    assert h.mohdith == "ابن حبان" and h.book == "المجروحين" and h.number_or_page == "1/489"
    assert h.grade == "باطل لا أصل له" and h.grade_class == "mawdu"
    assert h.rawi == "أنس بن مالك" and h.hadith_id == "Onb9Z6zG" and h.has_alternate
    assert h.url == "https://dorar.net/h/Onb9Z6zG"
    assert not h.text.startswith("1")  # result numbering stripped
    assert {x.grade_class for x in hits[1:]} == {"daif"}


def test_parse_alternate_page():
    blocks = parse_h_page(ALTS_HTML)
    assert len(blocks) == 2
    alt = blocks[1]
    assert alt.mohdith == "الألباني" and alt.grade == "إسناده موقوف حسن" and alt.grade_class == "hasan"


def test_search_is_cached(memory_cache):
    calls = []

    def handler(url, timeout):
        calls.append(url)
        return serve(url, timeout)

    c = mock_client(handler)
    a = c.search("اطلبوا العلم ولو بالصين")
    b = c.search("اُطلبوا العلمَ ولو بالصين!")  # normalizes to the same cache key
    assert len(calls) == 1 and [h.text for h in a] == [h.text for h in b]
    assert any(k.startswith("search:") for k in memory_cache)


def test_alternate():
    c = mock_client(serve)
    alt = c.alternate("Onb9Z6zG")
    assert alt is not None and alt.grade_class == "hasan"


def test_offline_mode_uses_cache_only(memory_cache):
    online = mock_client(serve)
    online.search("اطلبوا العلم ولو بالصين")
    offline = mock_client(lambda u, t: pytest.fail("network used in offline mode"), offline=True)
    assert offline.search("اطلبوا العلم ولو بالصين")
    with pytest.raises(DorarUnavailable):
        offline.search("استعلام غير مخزن")


def test_cloudflare_block_raises_unavailable():
    def blocked(url, timeout):
        raise FetchError(403, "HTTP 403")

    with pytest.raises(DorarUnavailable):
        mock_client(blocked).search("اي نص")


def test_timeouts_retry_then_unavailable(monkeypatch):
    monkeypatch.setattr(dorar.time, "sleep", lambda s: None)
    n = []

    def handler(url, timeout):
        n.append(1)
        raise FetchError(None, "timed out")

    with pytest.raises(DorarUnavailable):
        mock_client(handler).search("اي نص")
    assert len(n) == dorar.RETRIES + 1
