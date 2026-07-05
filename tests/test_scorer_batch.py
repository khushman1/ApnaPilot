"""Tests for applypilot.scoring.scorer: score_job, run_scoring batch processing."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


from applypilot.scoring.scorer import SCORE_PROMPT, score_job


# ── score_job ───────────────────────────────────────────────────────────

class TestScoreJob:
    def test_scores_valid_job(self) -> None:
        job = {
            "title": "Python Developer",
            "site": "Google",
            "location": "Toronto",
            "full_description": "Looking for a Python developer with API experience.",
        }
        with patch("applypilot.scoring.scorer.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.return_value = "SCORE: 85\nKEYWORDS: Python, API\nREASONING: Strong match."
            mock_get_client.return_value = mock_client

            result = score_job("Python | API experience", job)
            assert result["score"] == 85
            assert "Python" in result["keywords"]
            mock_client.chat.assert_called_once()

    def test_scores_with_messages_format(self) -> None:
        job = {
            "title": "SWE",
            "site": "Meta",
            "location": "Remote",
            "full_description": "Build things.",
        }
        with patch("applypilot.scoring.scorer.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.return_value = "SCORE: 72\nKEYWORDS: coding\nREASONING: Good."
            mock_get_client.return_value = mock_client

            score_job("Resume text", job)

            # Verify message format
            call_args = mock_client.chat.call_args
            messages = call_args[0][0]
            assert messages[0]["role"] == "system"
            assert SCORE_PROMPT in messages[0]["content"]
            assert messages[1]["role"] == "user"
            assert "SWE" in messages[1]["content"]

    def test_returns_zero_on_llm_error(self) -> None:
        job = {
            "title": "Engineer",
            "site": "Apple",
            "location": "Cupertino",
            "full_description": "Build iPhones.",
        }
        with patch("applypilot.scoring.scorer.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.return_value = "SCORE: 80\nKEYWORDS: Go\nREASONING: Strong."
            mock_get_client.return_value = mock_client

            result = score_job("Resume", job)
            assert result["score"] == 80

    def test_truncates_long_description(self) -> None:
        job = {
            "title": "SWE",
            "site": "Amazon",
            "location": "Seattle",
            "full_description": "A" * 7000,
        }
        with patch("applypilot.scoring.scorer.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.return_value = "SCORE: 60\nKEYWORDS: Java\nREASONING: OK."
            mock_get_client.return_value = mock_client

            score_job("Resume", job)

            call_args = mock_client.chat.call_args
            messages = call_args[0][0]
            # Description should be truncated to 6000 chars
            assert len(messages[1]["content"]) < 7500

    def test_handles_missing_location(self) -> None:
        job = {
            "title": "SWE",
            "site": "Startup",
            "full_description": "Build stuff.",
        }
        with patch("applypilot.scoring.scorer.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.return_value = "SCORE: 50\nKEYWORDS: Python\nREASONING: Mid."
            mock_get_client.return_value = mock_client

            result = score_job("Resume", job)
            assert result["score"] == 50

    def test_calls_with_correct_temperature(self) -> None:
        job = {"title": "SWE", "site": "Co", "full_description": "Test"}
        with patch("applypilot.scoring.scorer.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.return_value = "SCORE: 50\nKEYWORDS: x\nREASONING: y"
            mock_get_client.return_value = mock_client

            score_job("Resume", job)

            call_kwargs = mock_client.chat.call_args[1]
            assert call_kwargs["temperature"] == 0.2
            assert call_kwargs["max_tokens"] == 512
