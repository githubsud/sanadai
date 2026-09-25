"""In-memory sliding-window rate limits for the public deployment (per visitor IP + a global LLM cap).

Protects the CPU (verify requests) and the owner's LLM quota. When the LLM limit is reached the request still
works with the rule-based extractor; only the overall verify limit returns HTTP 429. A limit of 0 disables it.
"""

import threading
import time
from collections import defaultdict, deque

from app.config import get_settings


class SlidingWindow:
    def __init__(self, limit: int, window_s: float):
        self.limit = limit
        self.window_s = window_s
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        if self.limit <= 0:
            return True
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > self.window_s:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            if len(self._hits) > 10_000:  # bound memory: drop idle keys
                for k in [k for k, v in self._hits.items() if not v]:
                    del self._hits[k]
            return True


_limits: dict[str, SlidingWindow] = {}


def _get(name: str, limit: int, window_s: float) -> SlidingWindow:
    w = _limits.get(name)
    if w is None or w.limit != limit:
        w = _limits[name] = SlidingWindow(limit, window_s)
    return w


def allow_verify(client: str) -> bool:
    return _get("verify", get_settings().rate_verify_per_hour, 3600).allow(client)


def allow_llm(client: str) -> bool:
    """Per-visitor hourly LLM budget AND a global daily cap (the owner's API quota)."""
    s = get_settings()
    if not _get("llm_ip", s.rate_llm_per_hour, 3600).allow(client):
        return False
    return _get("llm_global", s.rate_llm_per_day_global, 86400).allow("global")


def reset() -> None:
    _limits.clear()
