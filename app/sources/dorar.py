"""Dorar.net (الدرر السنية) client — weak/fabricated hadith gradings and authentic alternatives.

A Python port of the endpoints and HTML parsing of github.com/AhmedElTabarani/dorar-hadith-api (MIT):
  search(text)        https://dorar.net/hadith/search?q=...      (non-specialist tab)
  alternate(id)       https://dorar.net/h/{id}?alts=1           (الصحيح البديل)
  similar(id)         https://dorar.net/h/{id}?sims=1           (أحاديث مشابهة)

Every response is stored permanently in the SQLite `dorar_cache` table, so the demo works offline
(DORAR_OFFLINE=true reads the cache only). Requests are rate-limited, retried, and time-bounded. All texts and
gradings are quoted verbatim from Dorar with attribution (muhaddith, book, page/number, url).

Transport note: dorar.net's Cloudflare rejects httpx requests (h11 sends lower-case header names) while
accepting the standard library's urllib, so fetching uses urllib; the fetcher is injectable for tests.
"""

import logging
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass

from bs4 import BeautifulSoup, Tag

from app.config import get_settings
from app.core.grades import classify_label_ar
from app.core.normalize import normalize_ar
from app.db import repo

log = logging.getLogger(__name__)

BASE = "https://dorar.net"
HEADERS = {
    # dorar.net sits behind Cloudflare, which rejects non-browser user agents.
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/128.0 Safari/537.36",
    "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "ar,en;q=0.8",
    "Referer": "https://dorar.net/",
}
MIN_INTERVAL_S = 1.2
RETRIES = 2

_LABELS = {
    "rawi": "الراوي",
    "mohdith": "المحدث",
    "book": "المصدر",
    "number_or_page": "الصفحة أو الرقم",
    "grade": "خلاصة حكم المحدث",
    "degree": "درجة الحديث",
    "takhrij": "التخريج",
}
_H_ID = re.compile(r"/h/([A-Za-z0-9]+)")
_LEADING_NUM = re.compile(r"^\s*\d*\s*-\s*:?\s*")


class DorarUnavailable(Exception):
    """Network error, Cloudflare block, or offline mode with a cache miss."""


@dataclass
class DorarHadith:
    text: str
    rawi: str = ""
    mohdith: str = ""
    book: str = ""
    number_or_page: str = ""
    grade: str = ""
    takhrij: str = ""
    hadith_id: str | None = None
    has_alternate: bool = False
    has_similar: bool = False

    @property
    def grade_class(self) -> str:
        return classify_label_ar(self.grade)

    @property
    def url(self) -> str | None:
        return f"{BASE}/h/{self.hadith_id}" if self.hadith_id else None

    def as_dict(self) -> dict:
        d = asdict(self)
        d["grade_class"] = self.grade_class
        d["url"] = self.url
        d["text_norm"] = normalize_ar(self.text)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "DorarHadith":
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__ if k in d})


# ---------------- parsing ----------------

def _clean(t: str) -> str:
    return re.sub(r"\s+", " ", t or "").strip()


def parse_block(block: Tag) -> DorarHadith | None:
    """One `.border-bottom` result block -> DorarHadith."""
    head = block.find(["h5", "article"])
    if head is None:
        return None
    text = _LEADING_NUM.sub("", _clean(head.get_text(" ")))
    text = re.sub(r"\s+([،,.:؛])", r"\1", text)
    if not text:
        return None
    fields: dict[str, str] = {}
    for strong in block.find_all("strong"):
        label = _clean(strong.get_text(" ").split(":")[0].replace("|", ""))
        span = strong.find("span")
        if span is None:
            continue
        for key, expected in _LABELS.items():
            if label == expected and key not in fields:
                fields[key] = _clean(span.get_text(" "))
    hid = None
    has_alt = has_sim = False
    for a in block.find_all("a", href=True):
        href = a["href"]
        if (m := _H_ID.search(href)) and hid is None:
            hid = m.group(1)
        has_alt |= href.endswith("?alts=1")
        has_sim |= href.endswith("?sims=1")
    if hid is None and (tagged := block.find("a", attrs={"tag": True})):
        hid = tagged["tag"]
    return DorarHadith(
        text=text, rawi=fields.get("rawi", ""), mohdith=fields.get("mohdith", ""), book=fields.get("book", ""),
        number_or_page=fields.get("number_or_page", ""), grade=fields.get("grade") or fields.get("degree", ""),
        takhrij=fields.get("takhrij", ""), hadith_id=hid, has_alternate=has_alt, has_similar=has_sim,
    )


def parse_search(html: str) -> list[DorarHadith]:
    soup = BeautifulSoup(html, "html.parser")
    scope = soup.select_one("#home") or soup
    return [h for b in scope.select(".border-bottom") if (h := parse_block(b))]


def parse_h_page(html: str) -> list[DorarHadith]:
    soup = BeautifulSoup(html, "html.parser")
    return [h for b in soup.select(".border-bottom") if (h := parse_block(b))]


# ---------------- client ----------------

class FetchError(Exception):
    def __init__(self, status: int | None, msg: str):
        super().__init__(msg)
        self.status = status


Fetcher = Callable[[str, float], str]


def urllib_fetch(url: str, timeout: float) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - fixed https host
            return r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raise FetchError(e.code, f"HTTP {e.code}") from e
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise FetchError(None, str(e)) from e


class DorarClient:
    def __init__(self, offline: bool | None = None, timeout: float | None = None, fetch: Fetcher | None = None):
        s = get_settings()
        self.offline = s.dorar_offline if offline is None else offline
        self.timeout = timeout or s.dorar_timeout_s
        self._fetch = fetch or urllib_fetch
        self._lock = threading.Lock()
        self._last = 0.0

    # --- low level ---
    def _get(self, url: str) -> str:
        if self.offline:
            raise DorarUnavailable("offline mode")
        err: Exception | None = None
        for attempt in range(RETRIES + 1):
            with self._lock:  # polite: at most one request per MIN_INTERVAL_S
                wait = self._last + MIN_INTERVAL_S - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                self._last = time.monotonic()
            try:
                return self._fetch(url, self.timeout)
            except FetchError as e:
                if e.status == 403:
                    raise DorarUnavailable("blocked by dorar.net (HTTP 403)") from e
                if e.status is not None and e.status < 500 and e.status != 429:
                    raise DorarUnavailable(f"dorar.net error HTTP {e.status}") from e
                err = e
                time.sleep(0.8 * (attempt + 1))
        raise DorarUnavailable(f"dorar.net unreachable: {err}")

    def _cached(self, key: str, endpoint: str, url: str, parser) -> list[DorarHadith]:
        hit = repo.cache_get(key)
        if hit is not None:
            return [DorarHadith.from_dict(d) for d in hit]
        items = parser(self._get(url))
        repo.cache_put(key, endpoint, [h.as_dict() for h in items])
        return items

    # --- endpoints ---
    def search(self, text: str) -> list[DorarHadith]:
        q = _clean(text)[:200]
        key = "search:" + normalize_ar(q)
        return self._cached(key, "search", f"{BASE}/hadith/search?{urllib.parse.urlencode({'q': q})}",
                            parse_search)

    def alternate(self, hadith_id: str) -> DorarHadith | None:
        """Dorar's 'authentic alternative' for a weak/fabricated hadith (second block of the page)."""
        items = self._cached(f"alts:{hadith_id}", "alternate", f"{BASE}/h/{hadith_id}?alts=1", parse_h_page)
        return items[1] if len(items) > 1 else None

    def similar(self, hadith_id: str) -> list[DorarHadith]:
        return self._cached(f"sims:{hadith_id}", "similar", f"{BASE}/h/{hadith_id}?sims=1", parse_h_page)

    def reachable(self) -> bool:
        if self.offline:
            return False
        try:
            self._fetch(f"{BASE}/robots.txt", 4)
            return True
        except FetchError:
            return False


_default: DorarClient | None = None


def client() -> DorarClient:
    global _default
    if _default is None:
        _default = DorarClient()
    return _default
