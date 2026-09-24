"""LLM provider interface (swappable) + Anthropic implementation.

The LLM is used ONLY for structured claim extraction and OCR (P3). It never grades, rules, or produces sacred text;
callers validate every output with Pydantic and verify that extracted spans exist verbatim in the user's input.
"""

import json
import logging
from typing import Protocol

from app.config import get_settings

log = logging.getLogger(__name__)


class LLMError(Exception):
    pass


class LLMProvider(Protocol):
    name: str

    @property
    def available(self) -> bool: ...

    def json(self, system: str, content: list[dict], schema: dict, max_tokens: int = 4096) -> dict:
        """Return a JSON object conforming to `schema`, or raise LLMError."""
        ...


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str | None = None, model: str | None = None, timeout: float = 45.0):
        s = get_settings()
        self.api_key = api_key if api_key is not None else s.anthropic_api_key
        self.model = model or s.llm_model
        self.timeout = timeout
        self._client = None

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def _get_client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(api_key=self.api_key, timeout=self.timeout, max_retries=1)
        return self._client

    def json(self, system: str, content: list[dict], schema: dict, max_tokens: int = 4096) -> dict:
        if not self.available:
            raise LLMError("ANTHROPIC_API_KEY not configured")
        import anthropic

        try:
            resp = self._get_client().messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": content}],
                # Extraction/OCR are simple, latency-sensitive tasks: low effort, schema-constrained JSON.
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
            )
        except anthropic.APIConnectionError as e:
            raise LLMError(f"connection error: {e}") from e
        except anthropic.RateLimitError as e:
            raise LLMError("rate limited") from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"API error {e.status_code}: {e.message}") from e
        if resp.stop_reason == "refusal":
            raise LLMError("model declined the request")
        if resp.stop_reason == "max_tokens":
            raise LLMError("output truncated (max_tokens)")
        text = next((b.text for b in resp.content if b.type == "text"), "")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMError(f"invalid JSON: {e}") from e


_provider: LLMProvider | None = None


def get_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        _provider = AnthropicProvider()
    return _provider


def set_provider(p: LLMProvider | None) -> None:
    """For tests / alternative backends."""
    global _provider
    _provider = p
