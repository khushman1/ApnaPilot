"""Tests for applypilot.pipeline: stage ordering, resolution, count_pending, execution."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from applypilot.pipeline import (
    DEFAULT_RUN_STAGES,
    STAGE_ORDER,
    STAGE_META,
    _UPSTREAM,
    _PENDING_SQL,
    _StageTracker,
    _count_pending,
    _resolve_stages,
    run_pipeline,
)

_FAKE_STATS = {
    "total": 10,
    "pending_detail": 5,
    "with_description": 8,
    "scored": 8,
    "tailored": 5,
    "with_cover_letter": 4,
    "ready_to_apply": 4,
    "applied": 2,
    "unscored": 2,
    "score_distribution": [],
    "score_buckets": [],
}


# ── Constants ─────────────────────────────────────────────────────────────

class TestPipelineConstants:
    def test_stage_order(self) -> None:
        assert STAGE_ORDER == ("discover", "enrich", "score", "tailor", "cover", "pdf")

    def test_default_run_stages(self) -> None:
        assert DEFAULT_RUN_STAGES == ("discover", "enrich", "score")

    def test_stage_meta_keys(self) -> None:
        for stage in STAGE_ORDER:
            assert stage in STAGE_META
            assert "desc" in STAGE_META[stage]

    def test_upstream_dependencies(self) -> None:
        assert _UPSTREAM["discover"] is None
        assert _UPSTREAM["enrich"] == "discover"
        assert _UPSTREAM["score"] == "enrich"
        assert _UPSTREAM["tailor"] == "score"
        assert _UPSTREAM["cover"] == "tailor"
        assert _UPSTREAM["pdf"] == "cover"

    def test_pending_sql_defined(self) -> None:
        for stage in ("enrich", "score", "tailor", "cover", "pdf"):
            assert stage in _PENDING_SQL
            assert "SELECT COUNT" in _PENDING_SQL[stage]

    def test_pending_sql_tailor_has_min_score_param(self) -> None:
        assert "?" in _PENDING_SQL["tailor"]
        assert "fit_score >=" in _PENDING_SQL["tailor"]


# ── _resolve_stages ──────────────────────────────────────────────────────

class TestResolveStages:
    def test_resolves_all_to_full_order(self) -> None:
        result = _resolve_stages(["all"])
        assert result == list(STAGE_ORDER)

    def test_validates_order(self) -> None:
        result = _resolve_stages(["pdf", "score", "discover"])
        # Should be in canonical order
        assert result == ["discover", "score", "pdf"]

    def test_removes_duplicates(self) -> None:
        result = _resolve_stages(["score", "score", "enrich"])
        assert result == ["enrich", "score"]

    def test_unknown_stage_exits(self) -> None:
        with pytest.raises(SystemExit):
            _resolve_stages(["invalid_stage"])

    def test_single_stage(self) -> None:
        result = _resolve_stages(["cover"])
        assert result == ["cover"]


# ── _StageTracker ────────────────────────────────────────────────────────

class TestStageTracker:
    def test_init_creates_events_for_all_stages(self) -> None:
        tracker = _StageTracker()
        for stage in STAGE_ORDER:
            assert not tracker.is_done(stage)

    def test_mark_done_sets_event(self) -> None:
        tracker = _StageTracker()
        tracker.mark_done("score", {"status": "ok"})
        assert tracker.is_done("score")

    def test_mark_done_with_no_result(self) -> None:
        tracker = _StageTracker()
        tracker.mark_done("enrich")
        assert tracker.is_done("enrich")

    def test_wait_returns_true_when_done(self) -> None:
        tracker = _StageTracker()
        tracker.mark_done("discover")
        assert tracker.wait("discover", timeout=1) is True

    def test_wait_returns_false_when_not_done(self) -> None:
        tracker = _StageTracker()
        assert tracker.wait("score", timeout=0.1) is False

    def test_get_results(self) -> None:
        tracker = _StageTracker()
        tracker.mark_done("score", {"status": "ok"})
        tracker.mark_done("tailor", {"status": "partial"})
        results = tracker.get_results()
        assert results["score"]["status"] == "ok"
        assert results["tailor"]["status"] == "partial"


# ── _count_pending ───────────────────────────────────────────────────────

class TestCountPending:
    @patch("applypilot.pipeline.get_connection")
    def test_counts_enrich_pending(self, mock_get_conn) -> None:
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = (5,)
        mock_get_conn.return_value = mock_conn

        count = _count_pending("enrich")
        assert count == 5
        mock_conn.execute.assert_called_once_with(_PENDING_SQL["enrich"])

    @patch("applypilot.pipeline.get_connection")
    def test_counts_tailor_with_min_score(self, mock_get_conn) -> None:
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = (3,)
        mock_get_conn.return_value = mock_conn

        count = _count_pending("tailor", min_score=80)
        assert count == 3
        mock_conn.execute.assert_called_once_with(_PENDING_SQL["tailor"], (80,))

    def test_returns_zero_for_unknown_stage(self) -> None:
        count = _count_pending("unknown_stage")
        assert count == 0

    def test_returns_zero_for_discover(self) -> None:
        count = _count_pending("discover")
        assert count == 0


# ── run_pipeline ─────────────────────────────────────────────────────────

class TestRunPipeline:
    @patch("applypilot.pipeline._run_sequential")
    @patch("applypilot.pipeline._resolve_stages")
    @patch("applypilot.pipeline.get_stats")
    @patch("applypilot.pipeline.init_db")
    @patch("applypilot.pipeline.ensure_dirs")
    @patch("applypilot.pipeline.load_env")
    def test_runs_default_stages_sequential(
        self,
        mock_load_env,
        mock_ensure_dirs,
        mock_init_db,
        mock_get_stats,
        mock_resolve,
        mock_sequential,
    ) -> None:
        mock_resolve.return_value = ["discover", "enrich", "score"]
        mock_get_stats.return_value = _FAKE_STATS
        mock_sequential.return_value = {"stages": [], "errors": {}, "elapsed": 1.0}

        result = run_pipeline()

        mock_resolve.assert_called_once_with(["discover", "enrich", "score"])
        mock_sequential.assert_called_once()
        assert result["elapsed"] == 1.0

    @patch("applypilot.pipeline._run_streaming")
    @patch("applypilot.pipeline._resolve_stages")
    @patch("applypilot.pipeline.get_stats")
    @patch("applypilot.pipeline.init_db")
    @patch("applypilot.pipeline.ensure_dirs")
    @patch("applypilot.pipeline.load_env")
    def test_runs_streaming_mode(
        self,
        mock_load_env,
        mock_ensure_dirs,
        mock_init_db,
        mock_get_stats,
        mock_resolve,
        mock_streaming,
    ) -> None:
        mock_resolve.return_value = ["discover", "enrich", "score"]
        mock_get_stats.return_value = _FAKE_STATS
        mock_streaming.return_value = {"stages": [], "errors": {}, "elapsed": 2.0}

        result = run_pipeline(stream=True)

        mock_streaming.assert_called_once()
        assert result["elapsed"] == 2.0

    @patch("applypilot.pipeline._run_sequential")
    @patch("applypilot.pipeline._resolve_stages")
    @patch("applypilot.pipeline.get_stats")
    @patch("applypilot.pipeline.init_db")
    @patch("applypilot.pipeline.ensure_dirs")
    @patch("applypilot.pipeline.load_env")
    def test_dry_run_skips_execution(
        self,
        mock_load_env,
        mock_ensure_dirs,
        mock_init_db,
        mock_get_stats,
        mock_resolve,
        mock_sequential,
    ) -> None:
        mock_resolve.return_value = ["score", "tailor"]
        mock_get_stats.return_value = _FAKE_STATS

        result = run_pipeline(stages=["score", "tailor"], dry_run=True)

        mock_sequential.assert_not_called()
        assert result["stages"] == []
        assert result["elapsed"] == 0.0

    @patch("applypilot.pipeline._run_sequential")
    @patch("applypilot.pipeline._resolve_stages")
    @patch("applypilot.pipeline.get_stats")
    @patch("applypilot.pipeline.init_db")
    @patch("applypilot.pipeline.ensure_dirs")
    @patch("applypilot.pipeline.load_env")
    def test_passes_min_score_to_sequential(
        self,
        mock_load_env,
        mock_ensure_dirs,
        mock_init_db,
        mock_get_stats,
        mock_resolve,
        mock_sequential,
    ) -> None:
        mock_resolve.return_value = ["score", "tailor"]
        mock_get_stats.return_value = _FAKE_STATS
        mock_sequential.return_value = {"stages": [], "errors": {}, "elapsed": 0.5}

        run_pipeline(stages=["score", "tailor"], min_score=85)

        call_args = mock_sequential.call_args
        assert call_args[0][1] == 85  # min_score positional arg

    @patch("applypilot.pipeline._run_sequential")
    @patch("applypilot.pipeline._resolve_stages")
    @patch("applypilot.pipeline.get_stats")
    @patch("applypilot.pipeline.init_db")
    @patch("applypilot.pipeline.ensure_dirs")
    @patch("applypilot.pipeline.load_env")
    def test_passes_workers_to_sequential(
        self,
        mock_load_env,
        mock_ensure_dirs,
        mock_init_db,
        mock_get_stats,
        mock_resolve,
        mock_sequential,
    ) -> None:
        mock_resolve.return_value = ["discover", "enrich"]
        mock_get_stats.return_value = _FAKE_STATS
        mock_sequential.return_value = {"stages": [], "errors": {}, "elapsed": 0.5}

        run_pipeline(stages=["discover", "enrich"], workers=4)

        call_kwargs = mock_sequential.call_args[1]
        assert call_kwargs["workers"] == 4
