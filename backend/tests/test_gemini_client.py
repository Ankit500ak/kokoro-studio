"""Unit tests for the Gemini client (app.services.gemini_client).

Gemini is the sole AI provider. These tests pin the calling contract the
pipeline was built against: OpenAI-shaped chat-completions requests against
the AI Studio compatibility endpoint, content extraction from the response
wrapper, None on failure, JSON mode for structured schemas, and the default
payload fallback in generate_structured. The HTTP layer is stubbed - nothing
here touches the network or needs a real API key.
"""

import asyncio
import json

import httpx
import pytest

from app.services.gemini_client import GeminiClient


def _client(api_key="test-key"):
    client = GeminiClient()
    client.api_key = api_key
    client.base_url = "https://gemini.test/v1beta/openai"
    client.model = "gemini-test-model"
    return client


class _FakeHTTP:
    """Stand-in for httpx.AsyncClient that records posts and replays responses."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def post(self, url, headers=None, json=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        return self._responses.pop(0)


def _stub_transport(monkeypatch, client, responses):
    fake = _FakeHTTP(responses)

    async def fake_get_client():
        return fake

    monkeypatch.setattr(client, "_get_client", fake_get_client)
    return fake


_REQ = httpx.Request("POST", "https://gemini.test/v1beta/openai/chat/completions")


def _ok_response(content):
    return httpx.Response(
        200,
        request=_REQ,
        json={
            "choices": [
                {
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ]
        },
    )


# ── generate: request shaping + response parsing ────────────


def test_generate_posts_openai_shaped_payload_and_returns_content(monkeypatch):
    client = _client()
    fake = _stub_transport(monkeypatch, client, [_ok_response("A story.")])

    result = asyncio.run(client.generate("You are a writer.", "Write a hook."))

    assert result == "A story."
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["url"] == "https://gemini.test/v1beta/openai/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer test-key"
    payload = call["json"]
    assert payload["model"] == "gemini-test-model"
    assert payload["messages"] == [
        {"role": "system", "content": "You are a writer."},
        {"role": "user", "content": "Write a hook."},
    ]
    assert payload["max_tokens"] == client.max_tokens
    # Thinking defaults to low effort so structured calls stay fast.
    assert payload["reasoning_effort"] == "low"
    assert "response_format" not in payload


def test_generate_missing_key_returns_none_without_http(monkeypatch):
    client = _client(api_key="")
    fake = _stub_transport(monkeypatch, client, [_ok_response("unused")])

    result = asyncio.run(client.generate("sys", "user"))

    assert result is None
    assert fake.calls == []


def test_generate_permanent_error_returns_none_without_retry(monkeypatch):
    client = _client()
    fake = _stub_transport(
        monkeypatch,
        client,
        [httpx.Response(404, request=_REQ, json={"error": "no model"})],
    )

    result = asyncio.run(client.generate("sys", "user"))

    assert result is None
    assert len(fake.calls) == 1  # 404 is permanent - no second attempt


# ── generate_structured: JSON mode, parsing, defaults ───────


def test_generate_structured_uses_json_mode_and_parses_object(monkeypatch):
    client = _client()
    payload = {
        "overall_score": 88,
        "breakdown": {"hook_strength": 90},
        "suggestions": ["Tighten the opening"],
        "verdict": "strong",
    }
    fake = _stub_transport(monkeypatch, client, [_ok_response(json.dumps(payload))])

    result = asyncio.run(
        client.generate_structured("sys", "user", schema_key="quality_score")
    )

    assert result == payload
    assert fake.calls[0]["json"]["response_format"] == {"type": "json_object"}


def test_generate_structured_returns_default_payload_on_garbage(monkeypatch):
    client = _client()
    _stub_transport(monkeypatch, client, [_ok_response("definitely not json")])

    result = asyncio.run(
        client.generate_structured("sys", "user", schema_key="classification")
    )

    assert isinstance(result, dict)
    assert result["hook_category"] == "mystery"  # documented default payload


def test_generate_structured_draft_schema_skips_json_mode(monkeypatch):
    # The "draft" schema is a plain string: JSON mode must NOT be forced for
    # it. (A prose reply falls through to the default draft payload - the
    # exact behaviour the old NVIDIA client had; the contract is preserved.)
    client = _client()
    fake = _stub_transport(monkeypatch, client, [_ok_response("Once upon a time.")])

    result = asyncio.run(
        client.generate_structured("sys", "user", schema_key="draft")
    )

    assert "response_format" not in fake.calls[0]["json"]
    assert result == client._get_default_payload("draft")


def test_generate_structured_unknown_schema_returns_none(monkeypatch):
    client = _client()
    _stub_transport(monkeypatch, client, [_ok_response("{}")])

    result = asyncio.run(
        client.generate_structured("sys", "user", schema_key="no_such_schema")
    )

    assert result is None


# ── helpers the pipeline relies on ──────────────────────────


def test_strip_markdown_fences_unwraps_payload():
    fenced = 'Here you go:\n```json\n{"a": 1}\n```\nDone.'
    assert GeminiClient._strip_markdown_fences(fenced) == '{"a": 1}'
    assert GeminiClient._strip_markdown_fences("plain") == "plain"
