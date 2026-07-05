"""Tests for applypilot.llm: provider detection, client behavior, Gemini compat fallback."""

from __future__ import annotations

import pytest

from applypilot.llm import (
    _GEMINI_COMPAT_BASE,
    _GEMINI_NATIVE_BASE,
    LLMClient,
    _detect_provider,
    get_client,
)


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
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("LLM_URL", raising=False)
        client = get_client()
        assert isinstance(client, LLMClient)

    def test_get_client_reuses_instance(self, monkeypatch) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("LLM_URL", raising=False)
        client1 = get_client()
        client2 = get_client()
        assert client1 is client2