"""Tests for applypilot.llm: provider detection, client behavior, Gemini compat fallback."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from applypilot.llm import (
    LLMClient,
    _detect_provider,
    get_client,
)

# Helper to reset the singleton between tests
from applypilot import llm as llm_mod


def _reset_singleton() -> None:
    llm_mod._instance = None


# ── Provider detection ──────────────────────────────────────────────────


class TestDetectProvider:
    def test_gemini_key_sets_gemini_url(self, monkeypatch) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("LLM_URL", raising=False)
        base_url, model, api_key = _detect_provider()
        assert "generativelanguage" in base_url
        assert model == "gemini-2.0-flash"
        assert api_key == "test-gemini-key"

    def test_openai_key_sets_openai_url(self, monkeypatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("LLM_URL", raising=False)
        base_url, model, api_key = _detect_provider()
        assert base_url == "https://api.openai.com/v1"
        assert model == "gpt-4o-mini"
        assert api_key == "test-openai-key"

    def test_local_url_takes_precedence(self, monkeypatch) -> None:
        monkeypatch.setenv("LLM_URL", "http://localhost:11434/v1")
        monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
        monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
        base_url, model, api_key = _detect_provider()
        assert base_url == "http://localhost:11434/v1"
        assert model == "local-model"
        assert api_key == ""

    def test_no_provider_raises(self, monkeypatch) -> None:
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("LLM_URL", raising=False)
        with pytest.raises(RuntimeError, match="No LLM provider"):
            _detect_provider()

    def test_model_override(self, monkeypatch) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.setenv("LLM_MODEL", "gemini-2.5-pro")
        monkeypatch.delenv("LLM_URL", raising=False)
        base_url, model, api_key = _detect_provider()
        assert model == "gemini-2.5-pro"


class TestGetClient:
    def test_get_client_returns_llm_client(self, monkeypatch) -> None:
        _reset_singleton()
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("LLM_URL", raising=False)
        client = get_client()
        assert isinstance(client, LLMClient)

    def test_get_client_reuses_instance(self, monkeypatch) -> None:
        _reset_singleton()
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("LLM_URL", raising=False)
        client1 = get_client()
        client2 = get_client()
        assert client1 is client2


# ── _chat_native_gemini (2 tests) ───────────────────────────────────────


class TestChatNativeGemini:
    def test_sends_correct_payload(self) -> None:
        client = LLMClient("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.0-flash", "key")
        messages = [
            {"role": "system", "content": "Be helpful."},
            {"role": "user", "content": "Hello!"},
        ]

        mock_response = MagicMock()
        mock_response.json.return_value = {"candidates": [{"content": {"parts": [{"text": "Hi there!"}]}}]}
        mock_response.raise_for_status = lambda: None
        client._client.post = MagicMock(return_value=mock_response)

        result = client._chat_native_gemini(messages, temperature=0.7, max_tokens=100)

        assert result == "Hi there!"
        call_kwargs = client._client.post.call_args
        payload = call_kwargs[1]["json"]
        assert len(payload["contents"]) == 1
        assert payload["contents"][0]["role"] == "user"
        assert payload["systemInstruction"]["parts"][0]["text"] == "Be helpful."

    def test_maps_assistant_to_model_role(self) -> None:
        client = LLMClient("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.0-flash", "key")
        messages = [
            {"role": "user", "content": "What is 2+2?"},
            {"role": "assistant", "content": "4"},
            {"role": "user", "content": "What about 3+3?"},
        ]

        mock_response = MagicMock()
        mock_response.json.return_value = {"candidates": [{"content": {"parts": [{"text": "6"}]}}]}
        mock_response.raise_for_status = lambda: None
        client._client.post = MagicMock(return_value=mock_response)

        result = client._chat_native_gemini(messages, temperature=0.0, max_tokens=50)

        assert result == "6"
        call_kwargs = client._client.post.call_args
        payload = call_kwargs[1]["json"]
        contents = payload["contents"]
        assert contents[0]["role"] == "user"
        assert contents[1]["role"] == "model"  # assistant -> model
        assert contents[2]["role"] == "user"


# ── _chat_compat (2 tests) ──────────────────────────────────────────────


class TestChatCompat:
    def test_sends_openai_payload(self) -> None:
        client = LLMClient("https://api.openai.com/v1", "gpt-4o-mini", "sk-key")
        messages = [{"role": "user", "content": "Hello"}]

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "Hi!"}}]}
        mock_response.raise_for_status = lambda: None
        mock_response.status_code = 200
        client._client.post = MagicMock(return_value=mock_response)

        result = client._chat_compat(messages, temperature=0.5, max_tokens=100)

        assert result == "Hi!"
        call_kwargs = client._client.post.call_args
        payload = call_kwargs[1]["json"]
        assert payload["model"] == "gpt-4o-mini"
        assert payload["temperature"] == 0.5
        assert payload["max_tokens"] == 100

    def test_uses_correct_url_and_headers(self) -> None:
        client = LLMClient("https://api.openai.com/v1", "gpt-4o-mini", "sk-key")
        messages = [{"role": "user", "content": "Hello"}]

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "Response"}}]}
        mock_response.raise_for_status = lambda: None
        mock_response.status_code = 200
        client._client.post = MagicMock(return_value=mock_response)

        client._chat_compat(messages, temperature=0.0, max_tokens=50)

        call_args = client._client.post.call_args
        assert "chat/completions" in call_args[0][0]
        assert "Authorization" in call_args[1]["headers"]
        assert "Bearer sk-key" in call_args[1]["headers"]["Authorization"]


# ── chat retry loop (4 tests) ──────────────────────────────────────────


class TestChatRetryLoop:
    def test_retries_on_429(self) -> None:
        _reset_singleton()
        client = LLMClient("https://api.openai.com/v1", "gpt-4o-mini", "sk-key")

        # First call: raise HTTPStatusError for 429, second call: success
        resp_429 = MagicMock()
        resp_429.json.return_value = {"choices": [{"message": {"content": "Retry"}}]}
        resp_429.status_code = 429
        resp_429.headers = {"Retry-After": "0.01"}

        resp_200 = MagicMock()
        resp_200.json.return_value = {"choices": [{"message": {"content": "Success"}}]}
        resp_200.status_code = 200

        exc = httpx.HTTPStatusError("Rate limit", request=MagicMock(), response=resp_429)
        client._client.post = MagicMock(side_effect=[exc, resp_200])

        with patch("applypilot.llm.time.sleep"):
            result = client.chat([{"role": "user", "content": "test"}], temperature=0.0, max_tokens=50)

        assert result == "Success"
        assert client._client.post.call_count == 2

    def test_retries_on_timeout(self) -> None:
        _reset_singleton()
        client = LLMClient("https://api.openai.com/v1", "gpt-4o-mini", "sk-key")

        resp_200 = MagicMock()
        resp_200.json.return_value = {"choices": [{"message": {"content": "OK"}}]}
        resp_200.status_code = 200

        client._client.post = MagicMock(side_effect=[httpx.TimeoutException("timeout"), resp_200])

        with patch("applypilot.llm.time.sleep"):
            result = client.chat([{"role": "user", "content": "test"}], temperature=0.0, max_tokens=50)

        assert result == "OK"
        assert client._client.post.call_count == 2

    def test_retry_backoff_uses_sleep(self) -> None:
        """Retry backoff calls time.sleep with exponential delay (no Retry-After header)."""
        _reset_singleton()
        client = LLMClient("https://api.openai.com/v1", "gpt-4o-mini", "sk-key")

        # Two 429s with no Retry-After header, then success
        resp_429a = MagicMock()
        resp_429a.status_code = 429
        resp_429a.headers = {}
        resp_429b = MagicMock()
        resp_429b.status_code = 429
        resp_429b.headers = {}
        resp_200 = MagicMock()
        resp_200.json.return_value = {"choices": [{"message": {"content": "OK"}}]}
        resp_200.status_code = 200

        client._client.post = MagicMock(
            side_effect=[
                httpx.HTTPStatusError("Rate limit", request=MagicMock(), response=resp_429a),
                httpx.HTTPStatusError("Rate limit", request=MagicMock(), response=resp_429b),
                resp_200,
            ]
        )

        with patch("applypilot.llm.time.sleep") as mock_sleep:
            result = client.chat([{"role": "user", "content": "test"}], temperature=0.0, max_tokens=50)

        assert result == "OK"
        # Should have slept twice (exponential backoff: 10s, then 20s)
        assert mock_sleep.call_count == 2
        assert mock_sleep.call_args_list[0][0][0] == 10  # 10 * 2^0
        assert mock_sleep.call_args_list[1][0][0] == 20  # 10 * 2^1

    def test_gemini_403_fallback_to_native(self) -> None:
        """Gemini compat 403 triggers switch to native generateContent API."""
        _reset_singleton()
        # Use Gemini compat URL so _is_gemini is True
        client = LLMClient("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.0-flash", "key")

        # First call: 403 on compat endpoint
        resp_403 = MagicMock()
        resp_403.status_code = 403
        resp_403.text = "not found"
        resp_200 = MagicMock()
        resp_200.json.return_value = {"candidates": [{"content": {"parts": [{"text": "Native!"}]}}]}
        resp_200.raise_for_status = lambda: None

        post_calls = [0]

        def mock_post(*args, **kwargs):
            post_calls[0] += 1
            if post_calls[0] == 1:
                # First call: compat endpoint returns 403
                return resp_403
            return resp_200

        client._client.post = mock_post

        result = client.chat([{"role": "user", "content": "test"}], temperature=0.0, max_tokens=50)

        assert result == "Native!"
        assert client._use_native_gemini is True
        # Should have called post twice: once compat, once native
        assert post_calls[0] == 2
