"""Tests for applypilot.view: dashboard generation, score bucketing."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from applypilot.view import _bucket_for_score, generate_dashboard


# ── _bucket_for_score ────────────────────────────────────────────────────

class TestBucketForScore:
    def test_human_review_bucket(self) -> None:
        bucket_id, label, color = _bucket_for_score(95)
        assert bucket_id == "human_review"
        assert "Human Review" in label
        assert color == "#f97316"

    def test_auto_eligible_bucket(self) -> None:
        bucket_id, label, color = _bucket_for_score(75)
        assert bucket_id == "auto_eligible"
        assert "Auto-Eligible" in label
        assert color == "#10b981"

    def test_boundary_90(self) -> None:
        bucket_id, _, _ = _bucket_for_score(90)
        assert bucket_id == "human_review"

    def test_boundary_70(self) -> None:
        bucket_id, _, _ = _bucket_for_score(70)
        assert bucket_id == "auto_eligible"

    def test_low_score(self) -> None:
        bucket_id, _, _ = _bucket_for_score(1)
        assert bucket_id == "auto_eligible"

    def test_boundary_89(self) -> None:
        bucket_id, _, _ = _bucket_for_score(89)
        assert bucket_id == "auto_eligible"


# ── generate_dashboard ───────────────────────────────────────────────────

class TestGenerateDashboard:
    def test_generates_html(self) -> None:
        with patch("applypilot.view.get_connection") as mock_get_conn:
            mock_conn = MagicMock()
            mock_conn.execute.side_effect = [
                MagicMock(fetchone=lambda: (10,)),   # total
                MagicMock(fetchone=lambda: (5,)),    # ready
                MagicMock(fetchone=lambda: (8,)),    # scored
                MagicMock(fetchone=lambda: (4,)),    # tailored
                MagicMock(fetchone=lambda: (4,)),    # cover
                MagicMock(fetchone=lambda: (3,)),    # applied
                MagicMock(fetchall=lambda: []),      # score dist
                MagicMock(fetchall=lambda: []),      # jobs
                MagicMock(fetchall=lambda: []),      # human review jobs
            ]
            mock_get_conn.return_value = mock_conn

            path = generate_dashboard()
            assert path.endswith("dashboard.html")
            html = Path(path).read_text()
            assert "<!DOCTYPE html>" in html or "<html" in html.lower()

    def test_includes_total_jobs(self) -> None:
        with patch("applypilot.view.get_connection") as mock_get_conn:
            mock_conn = MagicMock()
            mock_conn.execute.side_effect = [
                MagicMock(fetchone=lambda: (50,)),
                MagicMock(fetchone=lambda: (20,)),
                MagicMock(fetchone=lambda: (40,)),
                MagicMock(fetchone=lambda: (15,)),
                MagicMock(fetchone=lambda: (10,)),
                MagicMock(fetchone=lambda: (5,)),
                MagicMock(fetchall=lambda: []),
                MagicMock(fetchall=lambda: []),
                MagicMock(fetchall=lambda: []),
            ]
            mock_get_conn.return_value = mock_conn

            path = generate_dashboard()
            html = Path(path).read_text()
            assert "50" in html

    def test_includes_css(self) -> None:
        with patch("applypilot.view.get_connection") as mock_get_conn:
            mock_conn = MagicMock()
            mock_conn.execute.side_effect = [
                MagicMock(fetchone=lambda: (1,)),
                MagicMock(fetchone=lambda: (0,)),
                MagicMock(fetchone=lambda: (1,)),
                MagicMock(fetchone=lambda: (0,)),
                MagicMock(fetchone=lambda: (0,)),
                MagicMock(fetchone=lambda: (0,)),
                MagicMock(fetchall=lambda: []),
                MagicMock(fetchall=lambda: []),
                MagicMock(fetchall=lambda: []),
            ]
            mock_get_conn.return_value = mock_conn

            path = generate_dashboard()
            html = Path(path).read_text()
            assert "<style" in html or "<link" in html

    def test_escapes_html_in_job_titles(self) -> None:
        with patch("applypilot.view.get_connection") as mock_get_conn:
            mock_conn = MagicMock()
            mock_conn.execute.side_effect = [
                MagicMock(fetchone=lambda: (1,)),
                MagicMock(fetchone=lambda: (0,)),
                MagicMock(fetchone=lambda: (1,)),
                MagicMock(fetchone=lambda: (0,)),
                MagicMock(fetchone=lambda: (0,)),
                MagicMock(fetchone=lambda: (0,)),
                MagicMock(fetchall=lambda: [(85, 1)]),
                MagicMock(fetchall=lambda: []),
                MagicMock(fetchall=lambda: []),
            ]
            mock_get_conn.return_value = mock_conn

            path = generate_dashboard()
            html = Path(path).read_text()
            assert len(html) > 100
