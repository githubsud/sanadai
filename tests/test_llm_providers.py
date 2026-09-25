"""LLM providers without network: Gemini request shape / schema conversion / errors, provider selection."""

import httpx
import pytest

from app.config import get_settings
from app.llm import prompts
from app.llm import provider as prov
from app.llm.provider import GeminiProvider, LLMError, to_gemini_schema


def test_schema_conversion_for_gemini():
    g = to_gemini_schema(prompts.EXTRACT_SCHEMA)
    item = g["properties"]["claims"]["items"]
    assert "additionalProperties" not in g and "additionalProperties" not in item
    assert item["properties"]["attributed_to"] == {"type": "STRING", "nullable": True}
    assert item["properties"]["claim_type"]["enum"] == ["quran", "hadith", "saying"]
    assert g["type"] == "OBJECT" and item["type"] == "OBJECT"


class Captured:
    def __init__(self, response: httpx.Response):
        self.response = response
        self.calls: list[dict] = []

    def __call__(self, url, json=None, timeout=None, headers=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        return self.response


def gemini_reply(text: str, finish="STOP") -> httpx.Response:
    return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": finish}]})


def test_gemini_request_and_parse(monkeypatch):
    cap = Captured(gemini_reply('{"claims": []}'))
    monkeypatch.setattr(httpx, "post", cap)
    p = GeminiProvider(api_key="test-key", model="gemini-x")
    content = [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "AAAA"}},
               {"type": "text", "text": "hello"}]
    assert p.json("sys", content, prompts.EXTRACT_SCHEMA) == {"claims": []}
    call = cap.calls[0]
    assert call["url"].endswith("/models/gemini-x:generateContent") and "test-key" not in call["url"]
    assert call["headers"]["x-goog-api-key"] == "test-key"
    body = call["json"]
    assert body["systemInstruction"]["parts"][0]["text"] == "sys"
    assert body["contents"][0]["parts"][0] == {"inline_data": {"mime_type": "image/png", "data": "AAAA"}}
    assert body["generationConfig"]["responseMimeType"] == "application/json"


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(400, json={"error": {"message": "API key not valid"}}),
        httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}}),
        httpx.Response(200, json={"candidates": []}),
        gemini_reply("{not json"),
        gemini_reply('{"claims": [', finish="MAX_TOKENS"),
    ],
)
def test_gemini_errors_raise_llmerror(monkeypatch, response):
    monkeypatch.setattr(httpx, "post", Captured(response))
    with pytest.raises(LLMError):
        GeminiProvider(api_key="k").json("s", [{"type": "text", "text": "x"}], prompts.OCR_SCHEMA)


def test_gemini_without_key_is_unavailable():
    p = GeminiProvider(api_key="")
    assert not p.available
    with pytest.raises(LLMError):
        p.json("s", [], prompts.OCR_SCHEMA)


@pytest.mark.parametrize(
    "choice,anthropic_key,gemini_key,expected",
    [("auto", "", "g", "gemini"), ("auto", "a", "g", "anthropic"), ("gemini", "a", "g", "gemini"),
     ("anthropic", "", "g", "anthropic"), ("auto", "", "", "anthropic")],
)
def test_provider_selection(monkeypatch, choice, anthropic_key, gemini_key, expected):
    s = get_settings()
    monkeypatch.setattr(s, "llm_provider", choice)
    monkeypatch.setattr(s, "anthropic_api_key", anthropic_key)
    monkeypatch.setattr(s, "gemini_api_key", gemini_key)
    prov.set_provider(None)
    try:
        assert prov.get_provider().name == expected
    finally:
        prov.set_provider(None)
