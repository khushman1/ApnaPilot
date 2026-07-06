"""Tests for applypilot.scoring.scorer: score parsing, scoring logic."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


from applypilot.scoring.scorer import SCORE_PROMPT, _parse_score_response, run_scoring, score_job


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


# ── score_job (2 tests) ──────────────────────────────────────────────────


class TestScoreJob:
    def test_scores_job_success(self) -> None:
        job = {"title": "Backend Eng", "site": "Indeed", "location": "NYC", "full_description": "Needs Python"}

        with patch("applypilot.scoring.scorer.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.return_value = "SCORE: 82\nKEYWORDS: Python\nREASONING: Good match."
            mock_get_client.return_value = mock_client

            result = score_job("resume text", job)

        assert result["score"] == 82
        assert "Python" in result["keywords"]
        assert "Good match" in result["reasoning"]

    def test_scores_job_llm_error(self) -> None:
        job = {"title": "Frontend Dev", "site": "LinkedIn", "location": "SF", "full_description": "React needed"}

        with patch("applypilot.scoring.scorer.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.side_effect = RuntimeError("API down")
            mock_get_client.return_value = mock_client

            result = score_job("resume text", job)

        assert result["score"] == 0
        assert result["keywords"] == ""
        assert "API down" in result["reasoning"]


# ── run_scoring (6 tests) ────────────────────────────────────────────────


def _make_job_row(url, title, site, location, desc):
    """Create a dict that mimics a sqlite3.Row converted to dict."""
    return {
        "url": url,
        "title": title,
        "site": site,
        "location": location,
        "full_description": desc,
        "salary": "",
        "description": "",
        "strategy": "",
        "discovered_at": "",
    }


class TestRunScoring:
    @patch("applypilot.scoring.scorer.get_connection")
    @patch("applypilot.scoring.scorer.RESUME_PATH")
    @patch("applypilot.scoring.scorer.score_job")
    @patch("applypilot.scoring.scorer.get_human_review_score", return_value=90)
    @patch("applypilot.scoring.scorer.webhook_configured", return_value=False)
    def test_scores_two_jobs_and_updates_db(
        self, mock_webhook, mock_hr_score, mock_score_job, mock_resume, mock_get_conn
    ) -> None:
        """Score 2 jobs and verify DB updates."""
        mock_resume.read_text.return_value = "My resume"
        jobs = [
            _make_job_row("https://job1.com", "Job1", "Indeed", "NYC", "desc1"),
            _make_job_row("https://job2.com", "Job2", "LinkedIn", "SF", "desc2"),
        ]
        mock_conn = MagicMock()
        # First fetchall: jobs; subsequent fetchalls: distribution tuples
        mock_conn.execute.return_value.fetchall.side_effect = [jobs, [(85, 2), (92, 1)]]
        mock_get_conn.return_value = mock_conn

        mock_score_job.side_effect = [
            {"score": 85, "keywords": "Python", "reasoning": "Good"},
            {"score": 92, "keywords": "Rust", "reasoning": "Great"},
        ]

        result = run_scoring()

        assert result["scored"] == 2
        assert result["errors"] == 0
        assert "elapsed" in result
        # DB should have been updated for both (UPDATE calls)
        update_calls = [c for c in mock_conn.execute.call_args_list if "UPDATE" in str(c)]
        assert len(update_calls) >= 2

    @patch("applypilot.scoring.scorer.get_connection")
    @patch("applypilot.scoring.scorer.RESUME_PATH")
    @patch("applypilot.scoring.scorer.score_job")
    def test_no_jobs(self, mock_score_job, mock_resume, mock_get_conn) -> None:
        """No pending jobs returns immediately."""
        mock_resume.read_text.return_value = "resume"
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_get_conn.return_value = mock_conn

        result = run_scoring()

        assert result["scored"] == 0
        assert result["errors"] == 0
        assert result["elapsed"] == 0.0
        mock_score_job.assert_not_called()

    @patch("applypilot.scoring.scorer.get_connection")
    @patch("applypilot.scoring.scorer.RESUME_PATH")
    @patch("applypilot.scoring.scorer.score_job")
    @patch("applypilot.scoring.scorer.get_human_review_score", return_value=90)
    @patch("applypilot.scoring.scorer.webhook_configured", return_value=False)
    def test_rescore_mode(self, mock_webhook, mock_hr_score, mock_score_job, mock_resume, mock_get_conn) -> None:
        """rescore=True re-scores all jobs, not just unscored."""
        mock_resume.read_text.return_value = "resume"
        mock_conn = MagicMock()
        jobs = [_make_job_row("https://job1.com", "Job1", "Indeed", "NYC", "desc")]
        mock_conn.execute.return_value.fetchall.side_effect = [jobs, [(80, 1)]]
        mock_get_conn.return_value = mock_conn
        mock_score_job.return_value = {"score": 80, "keywords": "Go", "reasoning": "OK"}

        result = run_scoring(rescore=True)

        assert result["scored"] == 1
        # Should have called execute with SELECT * FROM jobs WHERE full_description IS NOT NULL
        first_call = mock_conn.execute.call_args_list[0]
        assert "full_description IS NOT NULL" in first_call[0][0]

    @patch("applypilot.scoring.scorer.get_connection")
    @patch("applypilot.scoring.scorer.RESUME_PATH")
    @patch("applypilot.scoring.scorer.score_job")
    @patch("applypilot.scoring.scorer.get_human_review_score", return_value=90)
    @patch("applypilot.scoring.scorer.webhook_configured", return_value=False)
    def test_human_review_flag(self, mock_webhook, mock_hr_score, mock_score_job, mock_resume, mock_get_conn) -> None:
        """Jobs scoring >= human_review_score get human_review_required=1."""
        mock_resume.read_text.return_value = "resume"
        mock_conn = MagicMock()
        jobs = [_make_job_row("https://job1.com", "Job1", "Indeed", "NYC", "desc")]
        mock_conn.execute.return_value.fetchall.side_effect = [jobs, [(95, 1)]]
        mock_get_conn.return_value = mock_conn
        # Score 95 -> human review
        mock_score_job.return_value = {"score": 95, "keywords": "Python", "reasoning": "Strong"}

        result = run_scoring()

        assert result["scored"] == 1
        # Check the UPDATE call has human_review_required = 1
        update_calls = [c for c in mock_conn.execute.call_args_list if "UPDATE" in str(c)]
        assert len(update_calls) >= 1
        # UPDATE args: (score, reasoning, scored_at, human_review_required, reason, marked_at, synced_at, sync_error, url)
        update_args = update_calls[0][0][1]
        # human_review_required (4th positional) should be 1 for score >= human_review_score
        assert 1 in update_args
        assert len(update_args) == 9  # 8 SET values + 1 WHERE value
        assert update_args[3] == 1  # human_review_required position

    @patch("applypilot.scoring.scorer.get_connection")
    @patch("applypilot.scoring.scorer.RESUME_PATH")
    @patch("applypilot.scoring.scorer.score_job")
    @patch("applypilot.scoring.scorer.get_human_review_score", return_value=90)
    @patch("applypilot.scoring.scorer.sync_human_review_jobs")
    @patch("applypilot.scoring.scorer.webhook_configured", return_value=True)
    def test_webhook_sync(
        self, mock_webhook, mock_sync, mock_hr_score, mock_score_job, mock_resume, mock_get_conn
    ) -> None:
        """If webhook configured and jobs flagged, sync is called."""
        mock_resume.read_text.return_value = "resume"
        mock_conn = MagicMock()
        jobs = [_make_job_row("https://job1.com", "Job1", "Indeed", "NYC", "desc")]
        mock_conn.execute.return_value.fetchall.side_effect = [jobs, [(95, 1)]]
        mock_get_conn.return_value = mock_conn
        mock_score_job.return_value = {"score": 95, "keywords": "Python", "reasoning": "Strong"}
        mock_sync.return_value = {"status": "ok", "synced": 1, "errors": 0, "message": "synced"}

        result = run_scoring()

        assert result["scored"] == 1
        mock_sync.assert_called_once()

    @patch("applypilot.scoring.scorer.get_connection")
    @patch("applypilot.scoring.scorer.RESUME_PATH")
    @patch("applypilot.scoring.scorer.score_job")
    @patch("applypilot.scoring.scorer.get_human_review_score", return_value=90)
    @patch("applypilot.scoring.scorer.webhook_configured", return_value=False)
    def test_limit_param(self, mock_webhook, mock_hr_score, mock_score_job, mock_resume, mock_get_conn) -> None:
        """limit=1 with rescore=True should only score one job (SQL LIMIT)."""
        mock_resume.read_text.return_value = "resume"
        mock_conn = MagicMock()
        # Only return 1 job (simulating LIMIT 1 in SQL)
        jobs = [_make_job_row("https://job1.com", "Job1", "Indeed", "NYC", "desc")]
        mock_conn.execute.return_value.fetchall.side_effect = [jobs, [(80, 1)]]
        mock_get_conn.return_value = mock_conn
        mock_score_job.return_value = {"score": 80, "keywords": "Python", "reasoning": "OK"}

        # Use rescore=True so limit applies via SQL LIMIT clause
        result = run_scoring(limit=1, rescore=True)

        # Verify the query includes LIMIT
        first_call = mock_conn.execute.call_args_list[0]
        assert "LIMIT 1" in first_call[0][0]
        assert mock_score_job.call_count == 1
        assert result["scored"] == 1
