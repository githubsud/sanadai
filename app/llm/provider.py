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


def to_gemini_schema(schema: dict) -> dict:
    """JSON Schema -> the OpenAPI subset Gemini's responseSchema accepts (no additionalProperties, nullable)."""
    out: dict = {}
    for k, v in schema.items():
        if k == "additionalProperties":
            continue
        if k == "type" and isinstance(v, list):
            types = [t for t in v if t != "null"]
            out["type"] = types[0].upper() if types else "STRING"
            if "null" in v:
                out["nullable"] = True
        elif k == "type":
            out["type"] = v.upper()
        elif k == "properties":
            out["properties"] = {name: to_gemini_schema(sub) for name, sub in v.items()}
        elif k == "items":
            out["items"] = to_gemini_schema(v)
        else:
            out[k] = v
    return out


class GeminiProvider:
    """Google Gemini via its REST API (generateContent, JSON response schema). Same narrow use as above."""

    name = "gemini"
    BASE = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, api_key: str | None = None, model: str | None = None, timeout: float = 45.0):
        s = get_settings()
        self.api_key = api_key if api_key is not None else s.gemini_api_key
        self.model = model or s.gemini_model
        self.timeout = timeout

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    @staticmethod
    def _parts(content: list[dict]) -> list[dict]:
        parts = []
        for block in content:
            if block["type"] == "text":
                parts.append({"text": block["text"]})
            elif block["type"] == "image":
                src = block["source"]
                parts.append({"inline_data": {"mime_type": src["media_type"], "data": src["data"]}})
        return parts

    def json(self, system: str, content: list[dict], schema: dict, max_tokens: int = 4096) -> dict:
        if not self.available:
            raise LLMError("GEMINI_API_KEY not configured")
        import httpx

        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": self._parts(content)}],
            "generationConfig": {"responseMimeType": "application/json", "responseSchema": to_gemini_schema(schema),
                                 "maxOutputTokens": max_tokens, "temperature": 0},
        }
        try:
            r = httpx.post(f"{self.BASE}/models/{self.model}:generateContent", json=body, timeout=self.timeout,
                           headers={"x-goog-api-key": self.api_key})  # key in a header, never in the URL/logs
        except httpx.HTTPError as e:
            raise LLMError(f"connection error: {e}") from e
        if r.status_code != 200:
            msg = r.json().get("error", {}).get("message", "") if r.headers.get("content-type", "").startswith(
                "application/json") else ""
            raise LLMError(f"Gemini API error {r.status_code}: {msg[:200]}")
        data = r.json()
        if data.get("promptFeedback", {}).get("blockReason"):
            raise LLMError("request blocked by the model's safety filter")
        cands = data.get("candidates") or []
        if not cands:
            raise LLMError("empty response")
        if cands[0].get("finishReason") == "MAX_TOKENS":
            raise LLMError("output truncated (max tokens)")
        text = "".join(p.get("text", "") for p in cands[0].get("content", {}).get("parts", []))
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMError(f"invalid JSON: {e}") from e


_provider: LLMProvider | None = None


def get_provider() -> LLMProvider:
    """LLM_PROVIDER=anthropic | gemini | auto (auto: whichever key is configured, Anthropic first)."""
    global _provider
    if _provider is None:
        s = get_settings()
        choice = s.llm_provider.lower()
        if choice == "auto":
            choice = "anthropic" if s.anthropic_api_key else ("gemini" if s.gemini_api_key else "anthropic")
        _provider = GeminiProvider() if choice == "gemini" else AnthropicProvider()
    return _provider


def set_provider(p: LLMProvider | None) -> None:
    """For tests / alternative backends."""
    global _provider
    _provider = p
