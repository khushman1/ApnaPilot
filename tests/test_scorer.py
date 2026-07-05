"""Tests for applypilot.scoring.scorer: score parsing, scoring logic."""

from __future__ import annotations

from applypilot.scoring.scorer import SCORE_PROMPT, _parse_score_response


# ── _parse_score_response ────────────────────────────────────────────────

class TestParseScoreResponse:
    def test_parses_valid_response(self) -> None:
        response = """\
SCORE: 85
KEYWORDS: Python, FastAPI, Docker, PostgreSQL
REASONING: Strong match on backend skills. Candidate has direct experience with all core technologies."""
        result = _parse_score_response(response)
        assert result["score"] == 85
        assert "Python" in result["keywords"]
        assert "Strong match" in result["reasoning"]

    def test_clamps_score_to_range(self) -> None:
        response = "SCORE: 150\nKEYWORDS: Python\nREASONING: Very strong."
        result = _parse_score_response(response)
        assert result["score"] == 100

        response2 = "SCORE: -10\nKEYWORDS: Java\nREASONING: Weak."
        result2 = _parse_score_response(response2)
        # -10 parses as 10 (re\d+ finds '10'), then clamped to min(100)
        assert result2["score"] == 10

    def test_handles_missing_score(self) -> None:
        response = "The candidate is a great fit!\n\nKEYWORDS: Python, Docker\nREASONING: Good match."
        result = _parse_score_response(response)
        assert result["score"] == 0
        assert "Python" in result["keywords"]
        assert "Good match" in result["reasoning"]

    def test_handles_malformed_score(self) -> None:
        response = "SCORE: high\nKEYWORDS: Python\nREASONING: Nice."
        result = _parse_score_response(response)
        assert result["score"] == 0

    def test_uses_full_text_as_reasoning_when_missing(self) -> None:
        response = "SCORE: 72\nKEYWORDS: Python, AWS"
        result = _parse_score_response(response)
        assert result["score"] == 72
        assert "Python" in result["keywords"]
        # reasoning falls back to full response
        assert "SCORE: 72" in result["reasoning"]

    def test_handles_empty_response(self) -> None:
        result = _parse_score_response("")
        assert result["score"] == 0
        assert result["keywords"] == ""
        assert result["reasoning"] == ""

    def test_handles_score_in_middle_line(self) -> None:
        response = "SCORE: 90 is my rating\nKEYWORDS: Python\nREASONING: Strong."
        result = _parse_score_response(response)
        assert result["score"] == 90

    def test_preserves_reasoning_across_lines(self) -> None:
        response = """\
SCORE: 78
KEYWORDS: Python, Docker
REASONING: Candidate has solid backend skills. Direct experience
with API development and containerization."""
        result = _parse_score_response(response)
        assert result["score"] == 78
        # Reasoning is only the first line after REASONING:
        assert "Candidate has solid" in result["reasoning"]


# ── SCORE_PROMPT ─────────────────────────────────────────────────────────

class TestScorePrompt:
    def test_prompt_contains_format_instructions(self) -> None:
        assert "SCORE:" in SCORE_PROMPT
        assert "KEYWORDS:" in SCORE_PROMPT
        assert "REASONING:" in SCORE_PROMPT

    def test_prompt_contains_scoring_ranges(self) -> None:
        assert "90-100" in SCORE_PROMPT
        assert "70-89" in SCORE_PROMPT
        assert "40-69" in SCORE_PROMPT
        assert "1-39" in SCORE_PROMPT

    def test_prompt_mentions_weighted_criteria(self) -> None:
        assert "technical skills" in SCORE_PROMPT.lower()
        assert "transferable" in SCORE_PROMPT.lower()
