"""Tests for applypilot.llm: client creation, retry logic, provider detection."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from applypilot.llm import (
    LLMClient,
    _detect_provider,
    get_client,
)


# ── _detect_provider ────────────────────────────────────────────────────


class TestDetectProvider:
    def test_gemini_detected(self) -> None:
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            base_url, model, api_key = _detect_provider()
            assert "generativelanguage" in base_url
            assert api_key == "test-key"

    def test_openai_detected(self) -> None:
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test", "GEMINI_API_KEY": ""}):
            base_url, model, api_key = _detect_provider()
            assert "openai" in base_url
            assert api_key == "sk-test"

    def test_local_detected(self) -> None:
        with patch.dict("os.environ", {"LLM_URL": "http://localhost:8000"}):
            os_environ = {"LLM_URL": "http://localhost:8000", "GEMINI_API_KEY": "", "OPENAI_API_KEY": ""}
            with patch.dict("os.environ", os_environ, clear=True):
                base_url, model, api_key = _detect_provider()
                assert "localhost" in base_url

    def test_falls_back_to_gemini(self) -> None:
        # When no keys set, defaults to gemini
        os_environ = {"GEMINI_API_KEY": "test-key", "OPENAI_API_KEY": "", "LLM_URL": ""}
        with patch.dict("os.environ", os_environ, clear=True):
            base_url, model, api_key = _detect_provider()
            assert "generativelanguage" in base_url
            assert api_key == "test-key"


# ── LLMClient ───────────────────────────────────────────────────────────


class TestLLMClient:
    def test_creates_client(self) -> None:
        client = LLMClient("http://example.com", "test-model", "key")
        assert client.model == "test-model"
        assert client.api_key == "key"
        client.close()

    def test_uses_gemini_flag(self) -> None:
        client = LLMClient("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.5-flash", "key")
        assert client._is_gemini
        client.close()

    @patch.object(LLMClient, "_chat_compat")
    def test_chat_calls_compat(self, mock_compat) -> None:
        mock_compat.return_value = "Hello world"
        client = LLMClient("http://example.com", "test-model", "key")
        result = client.chat([{"role": "user", "content": "test"}])
        assert result == "Hello world"
        mock_compat.assert_called_once()
        client.close()

    @patch.object(LLMClient, "_chat_compat")
    def test_chat_with_temperature(self, mock_compat) -> None:
        mock_compat.return_value = "Result"
        client = LLMClient("http://example.com", "test-model", "key")
        client.chat([{"role": "user", "content": "test"}], temperature=0.5, max_tokens=256)
        # chat() passes temperature/max_tokens to _chat_compat
        mock_compat.assert_called_once()
        client.close()

    @patch.object(LLMClient, "_chat_compat")
    def test_chat_retries_on_429(self, mock_compat) -> None:
        import httpx

        resp1 = MagicMock()
        resp1.status_code = 429
        resp1.headers = {}
        mock_compat.side_effect = [
            httpx.HTTPStatusError("Rate limited", request=MagicMock(), response=resp1),
            "Result",
        ]
        client = LLMClient("http://example.com", "test-model", "key")
        with patch("time.sleep", return_value=None):
            result = client.chat([{"role": "user", "content": "test"}])
        assert result == "Result"
        assert mock_compat.call_count == 2
        client.close()

    @patch.object(LLMClient, "_chat_compat")
    def test_chat_retries_on_503(self, mock_compat) -> None:
        import httpx

        resp1 = MagicMock()
        resp1.status_code = 503
        resp1.headers = {}
        mock_compat.side_effect = [
            httpx.HTTPStatusError("Unavailable", request=MagicMock(), response=resp1),
            "Result",
        ]
        client = LLMClient("http://example.com", "test-model", "key")
        with patch("time.sleep", return_value=None):
            result = client.chat([{"role": "user", "content": "test"}])
        assert result == "Result"
        client.close()

    @patch.object(LLMClient, "_chat_compat")
    def test_chat_retries_on_timeout(self, mock_compat) -> None:
        mock_compat.side_effect = [httpx.TimeoutException("Timeout"), "Result"]
        client = LLMClient("http://example.com", "test-model", "key")
        with patch("time.sleep"):
            result = client.chat([{"role": "user", "content": "test"}])
        assert result == "Result"
        assert mock_compat.call_count == 2
        client.close()

    @patch.object(LLMClient, "_chat_compat")
    def test_chat_gemini_compat_fallback(self, mock_compat) -> None:
        from applypilot.llm import _GeminiCompatForbidden

        resp = MagicMock()
        mock_compat.side_effect = [_GeminiCompatForbidden(resp)]
        client = LLMClient("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.5-flash", "key")
        with patch.object(client, "_chat_native_gemini", return_value="Native result"):
            result = client.chat([{"role": "user", "content": "test"}])
        assert result == "Native result"
        client.close()

    def test_ask_convenience_method(self) -> None:
        client = LLMClient("http://example.com", "test-model", "key")
        with patch.object(client, "chat", return_value="Answer") as mock_chat:
            result = client.ask("What is 2+2?")
            assert result == "Answer"
            mock_chat.assert_called_once()
        client.close()


# ── get_client singleton ────────────────────────────────────────────────


class TestGetClient:
    def test_returns_same_instance(self) -> None:
        # Reset singleton
        from applypilot import llm as llm_mod

        llm_mod._instance = None
        try:
            with patch("applypilot.llm._detect_provider", return_value=("http://x.com", "m", "k")):
                c1 = get_client()
                c2 = get_client()
                assert c1 is c2
        finally:
            c1.close()
            llm_mod._instance = None
