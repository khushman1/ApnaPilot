"""Tests for applypilot.view: dashboard generation, score bucketing."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from applypilot.view import _bucket_for_score, generate_dashboard, open_dashboard


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


def _row(data: dict):
    """Build a dict-based mock row that supports key access like sqlite3.Row."""
    return data


# ── generate_dashboard ───────────────────────────────────────────────────


class TestGenerateDashboard:
    def test_generates_html(self) -> None:
        with (
            patch("applypilot.view.get_connection") as mock_get_conn,
            patch("applypilot.view.console") as mock_console,
        ):
            mock_conn = MagicMock()
            mock_conn.execute.side_effect = [
                MagicMock(fetchone=lambda: (10,)),  # total
                MagicMock(fetchone=lambda: (5,)),  # ready
                MagicMock(fetchone=lambda: (8,)),  # scored
                MagicMock(fetchone=lambda: (4,)),  # human_review
                MagicMock(fetchone=lambda: (3,)),  # auto_eligible
                MagicMock(fetchone=lambda: (1,)),  # skipped
                MagicMock(fetchone=lambda: (2,)),  # synced
                MagicMock(fetchall=lambda: []),  # site_stats
                MagicMock(fetchall=lambda: []),  # jobs
            ]
            mock_get_conn.return_value = mock_conn

            path = generate_dashboard()
            assert path.endswith("dashboard.html")
            html = Path(path).read_text()
            assert "<!DOCTYPE html>" in html or "<html" in html.lower()
            # Console should print dashboard path
            assert mock_console.print.called

    def test_includes_total_jobs(self) -> None:
        with patch("applypilot.view.get_connection") as mock_get_conn:
            mock_conn = MagicMock()
            mock_conn.execute.side_effect = [
                MagicMock(fetchone=lambda: (50,)),
                MagicMock(fetchone=lambda: (20,)),
                MagicMock(fetchone=lambda: (40,)),
                MagicMock(fetchone=lambda: (15,)),
                MagicMock(fetchone=lambda: (10,)),
                MagicMock(fetchone=lambda: (15,)),
                MagicMock(fetchone=lambda: (5,)),
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
                MagicMock(fetchone=lambda: (0,)),
                MagicMock(fetchall=lambda: []),
                MagicMock(fetchall=lambda: []),
            ]
            mock_get_conn.return_value = mock_conn

            path = generate_dashboard()
            html = Path(path).read_text()
            assert "<style" in html or "<link" in html

    def test_job_cards_with_human_review(self) -> None:
        """Dashboard includes job cards with human review metadata.

        Uses _build_dashboard_conn which yields results on demand for each
        execute() call, making the test resilient to query reordering.
        """

        def _build_dashboard_conn():
            """Build a mock connection that yields dashboard query results on demand."""
            results = iter(
                [
                    [(1,)],  # total
                    [(1,)],  # ready
                    [(1,)],  # scored
                    [(1,)],  # human_review (90+)
                    [(0,)],  # auto_eligible (70-89)
                    [(0,)],  # skipped (<70)
                    [(0,)],  # synced
                    [  # site_stats
                        _row({"site": "Indeed", "total": 1, "human_review": 1, "auto_eligible": 0, "avg_score": 95.0}),
                    ],
                    [  # jobs
                        _row(
                            {
                                "url": "https://job1.com",
                                "title": "Senior Python Eng",
                                "salary": "$150k",
                                "location": "Remote",
                                "site": "Indeed",
                                "full_description": "We need Python devs",
                                "application_url": "https://apply.com",
                                "fit_score": 95,
                                "score_reasoning": "Python, Django\nStrong match",
                                "human_review_required": 1,
                                "human_review_synced_at": None,
                                "human_review_sync_error": None,
                            }
                        ),
                    ],
                ]
            )
            mock_conn = MagicMock()

            def side_effect(sql):
                rows = next(results)
                mock_cur = MagicMock()
                mock_cur.fetchone.side_effect = lambda: rows[0] if len(rows) == 1 else rows[0]
                mock_cur.fetchall.return_value = rows
                return mock_cur

            mock_conn.execute.side_effect = side_effect
            return mock_conn

        with patch("applypilot.view.get_connection") as mock_get_conn:
            mock_get_conn.return_value = _build_dashboard_conn()

            path = generate_dashboard()
            html = Path(path).read_text()

            assert "Senior Python Eng" in html
            assert 'data-bucket="human_review"' in html
            assert 'data-score="95"' in html

    def test_job_cards_with_auto_eligible(self) -> None:
        """Dashboard includes job cards in auto-eligible bucket.

        Uses _build_dashboard_conn helper for resilient query handling.
        """

        def _build_dashboard_conn():
            """Build a mock connection that yields dashboard query results on demand."""
            results = iter(
                [
                    [(1,)],  # total
                    [(1,)],  # ready
                    [(1,)],  # scored
                    [(0,)],  # human_review (90+)
                    [(1,)],  # auto_eligible (70-89)
                    [(0,)],  # skipped (<70)
                    [(0,)],  # synced
                    [  # site_stats
                        _row(
                            {"site": "LinkedIn", "total": 1, "human_review": 0, "auto_eligible": 1, "avg_score": 78.0}
                        ),
                    ],
                    [  # jobs
                        _row(
                            {
                                "url": "https://job2.com",
                                "title": "Backend Dev",
                                "salary": "",
                                "location": "NYC",
                                "site": "LinkedIn",
                                "full_description": "React and Node",
                                "application_url": "",
                                "fit_score": 78,
                                "score_reasoning": "Node, React\nGood fit",
                                "human_review_required": 0,
                                "human_review_synced_at": None,
                                "human_review_sync_error": None,
                            }
                        ),
                    ],
                ]
            )
            mock_conn = MagicMock()

            def side_effect(sql):
                rows = next(results)
                mock_cur = MagicMock()
                mock_cur.fetchone.side_effect = lambda: rows[0] if len(rows) == 1 else rows[0]
                mock_cur.fetchall.return_value = rows
                return mock_cur

            mock_conn.execute.side_effect = side_effect
            return mock_conn

        with patch("applypilot.view.get_connection") as mock_get_conn:
            mock_get_conn.return_value = _build_dashboard_conn()

            path = generate_dashboard()
            html = Path(path).read_text()

            assert "Backend Dev" in html
            assert 'data-bucket="auto_eligible"' in html
            assert 'data-score="78"' in html


# ── open_dashboard ───────────────────────────────────────────────────────


class TestOpenDashboard:
    def test_opens_in_browser(self) -> None:
        """open_dashboard generates then opens in browser."""
        with (
            patch("applypilot.view.generate_dashboard") as mock_gen,
            patch("applypilot.view.webbrowser") as mock_browser,
            patch("applypilot.view.console"),
        ):
            mock_gen.return_value = "/tmp/dashboard.html"

            open_dashboard()

            mock_gen.assert_called_once_with(None)
            # webbrowser.open uses f"file:///{path}" so /tmp -> file:///tmp
            mock_browser.open.assert_called_once()
            call_arg = mock_browser.open.call_args[0][0]
            assert "dashboard.html" in call_arg
