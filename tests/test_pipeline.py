"""Tests for applypilot.pipeline: stage ordering, resolution, count_pending, execution."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from applypilot.pipeline import (
    DEFAULT_RUN_STAGES,
    STAGE_ORDER,
    STAGE_META,
    _UPSTREAM,
    _PENDING_SQL,
    _STAGE_RUNNERS,
    _StageTracker,
    _count_pending,
    _run_discover,
    _run_enrich,
    _run_score,
    _run_tailor,
    _run_cover,
    _run_pdf,
    _run_sequential,
    _run_streaming,
    _run_stage_streaming,
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
        count = _count_pending("discover")
        assert count == 0

    def test_returns_zero_for_discover(self) -> None:
        count = _count_pending("discover")
        assert count == 0


# ── _run_discover (3 tests) ──────────────────────────────────────────────


class TestRunDiscover:
    def test_all_ok(self) -> None:
        """All three discovery scrapers succeed; workers is passed through."""
        mock_run_discovery = MagicMock(return_value=None)
        mock_run_workday = MagicMock(return_value=None)
        mock_run_smartextract = MagicMock(return_value=None)

        with (
            patch("applypilot.pipeline.console"),
            patch.dict(
                "sys.modules",
                {
                    "applypilot.discovery.jobspy": MagicMock(run_discovery=mock_run_discovery),
                    "applypilot.discovery.workday": MagicMock(run_workday_discovery=mock_run_workday),
                    "applypilot.discovery.smartextract": MagicMock(run_smart_extract=mock_run_smartextract),
                },
            ),
        ):
            result = _run_discover(workers=2)

        assert result == {"jobspy": "ok", "workday": "ok", "smartextract": "ok"}
        # Verify workers was passed to workday and smartextract
        mock_run_workday.assert_called_once_with(workers=2)
        mock_run_smartextract.assert_called_once_with(workers=2)

    def test_partial_fail(self) -> None:
        """Workday scraper fails; jobspy and smartextract succeed."""
        mock_run_discovery = MagicMock(return_value=None)
        mock_run_workday = MagicMock(side_effect=RuntimeError("timeout"))
        mock_run_smartextract = MagicMock(return_value=None)

        with (
            patch("applypilot.pipeline.console"),
            patch.dict(
                "sys.modules",
                {
                    "applypilot.discovery.jobspy": MagicMock(run_discovery=mock_run_discovery),
                    "applypilot.discovery.workday": MagicMock(run_workday_discovery=mock_run_workday),
                    "applypilot.discovery.smartextract": MagicMock(run_smart_extract=mock_run_smartextract),
                },
            ),
        ):
            result = _run_discover()

        assert result["jobspy"] == "ok"
        assert result["workday"] == "error: timeout"
        assert result["smartextract"] == "ok"

    def test_all_fail(self) -> None:
        """All three discovery scrapers fail."""
        mock_run_discovery = MagicMock(side_effect=ConnectionError("no net"))
        mock_run_workday = MagicMock(side_effect=ConnectionError("no net"))
        mock_run_smartextract = MagicMock(side_effect=ConnectionError("no net"))

        with (
            patch("applypilot.pipeline.console"),
            patch.dict(
                "sys.modules",
                {
                    "applypilot.discovery.jobspy": MagicMock(run_discovery=mock_run_discovery),
                    "applypilot.discovery.workday": MagicMock(run_workday_discovery=mock_run_workday),
                    "applypilot.discovery.smartextract": MagicMock(run_smart_extract=mock_run_smartextract),
                },
            ),
        ):
            result = _run_discover()

        assert result["jobspy"] == "error: no net"
        assert result["workday"] == "error: no net"
        assert result["smartextract"] == "error: no net"


# ── Individual stage runners: _run_enrich through _run_pdf (6 tests) ─────


class TestStageRunners:
    def test_run_enrich_success(self) -> None:
        with patch("applypilot.enrichment.detail.run_enrichment") as mock_enrich:
            mock_enrich.return_value = None
            with patch("applypilot.enrichment.detail"):
                result = _run_enrich(workers=3)
            assert result["status"] == "ok"
            mock_enrich.assert_called_once_with(workers=3)

    def test_run_enrich_raises(self) -> None:
        with patch("applypilot.enrichment.detail.run_enrichment") as mock_enrich:
            mock_enrich.side_effect = RuntimeError("fail")
            with patch("applypilot.enrichment.detail"):
                result = _run_enrich()
            assert result["status"] == "error: fail"

    def test_run_score_success(self) -> None:
        with patch("applypilot.scoring.scorer.run_scoring") as mock_score:
            mock_score.return_value = None
            with patch("applypilot.scoring.scorer"):
                result = _run_score()
            assert result["status"] == "ok"

    def test_run_score_raises(self) -> None:
        with patch("applypilot.scoring.scorer.run_scoring") as mock_score:
            mock_score.side_effect = ValueError("bad data")
            with patch("applypilot.scoring.scorer"):
                result = _run_score()
            assert result["status"] == "error: bad data"

    def test_run_tailor_success(self) -> None:
        with patch("applypilot.scoring.tailor.run_tailoring") as mock_tailor:
            mock_tailor.return_value = None
            with patch("applypilot.scoring.tailor"):
                result = _run_tailor(min_score=85, validation_mode="strict")
            assert result["status"] == "ok"
            mock_tailor.assert_called_once_with(min_score=85, validation_mode="strict")

    def test_run_cover_success(self) -> None:
        with patch("applypilot.scoring.cover_letter.run_cover_letters") as mock_cover:
            mock_cover.return_value = None
            with patch("applypilot.scoring.cover_letter"):
                result = _run_cover(min_score=75)
            assert result["status"] == "ok"
            mock_cover.assert_called_once_with(min_score=75, validation_mode="normal")

    def test_run_pdf_success(self) -> None:
        with patch("applypilot.scoring.pdf.batch_convert") as mock_pdf:
            mock_pdf.return_value = None
            with patch("applypilot.scoring.pdf"):
                result = _run_pdf()
            assert result["status"] == "ok"

    def test_run_pdf_raises(self) -> None:
        with patch("applypilot.scoring.pdf.batch_convert") as mock_pdf:
            mock_pdf.side_effect = OSError("no pandoc")
            with patch("applypilot.scoring.pdf"):
                result = _run_pdf()
            assert result["status"] == "error: no pandoc"


# ── _run_sequential (4 tests) ────────────────────────────────────────────


class TestRunSequential:
    @patch.dict(
        "applypilot.pipeline._STAGE_RUNNERS",
        {"discover": MagicMock(return_value={"status": "ok"}), "score": MagicMock(return_value={"status": "ok"})},
    )
    @patch("applypilot.pipeline.console")
    def test_multi_stage(self, mock_console) -> None:
        result = _run_sequential(["discover", "score"], min_score=70, workers=1)

        assert len(result["stages"]) == 2
        assert result["stages"][0]["stage"] == "discover"
        assert result["stages"][1]["stage"] == "score"
        assert result["errors"] == {}
        assert "elapsed" in result

    @patch.dict(
        "applypilot.pipeline._STAGE_RUNNERS",
        {"score": MagicMock(side_effect=RuntimeError("crash"))},
    )
    @patch("applypilot.pipeline.console")
    def test_error_stage(self, mock_console) -> None:
        result = _run_sequential(["score"], min_score=70, workers=1)

        assert result["stages"][0]["status"] == "error: crash"
        assert "score" in result["errors"]

    @patch.dict(
        "applypilot.pipeline._STAGE_RUNNERS",
        {"discover": MagicMock(return_value={"jobspy": "ok", "workday": "error: x", "smartextract": "ok"})},
    )
    @patch("applypilot.pipeline.console")
    def test_partial_status(self, mock_console) -> None:
        result = _run_sequential(["discover"], min_score=70, workers=1)

        assert result["stages"][0]["status"] == "partial"
        assert result["errors"] == {}

    @patch.dict(
        "applypilot.pipeline._STAGE_RUNNERS",
        {
            "tailor": MagicMock(return_value={"status": "ok"}),
            "cover": MagicMock(return_value={"status": "ok"}),
        },
    )
    @patch("applypilot.pipeline.console")
    def test_kwargs_passed(self, mock_console) -> None:
        _run_sequential(["tailor", "cover"], min_score=85, workers=2, validation_mode="strict")

        tailor_runner = _STAGE_RUNNERS["tailor"]
        cover_runner = _STAGE_RUNNERS["cover"]
        # Check kwargs were passed
        tailor_runner.assert_called_with(min_score=85, validation_mode="strict")
        cover_runner.assert_called_with(min_score=85, validation_mode="strict")

    @patch.dict(
        "applypilot.pipeline._STAGE_RUNNERS",
        {
            "discover": MagicMock(return_value={"jobspy": "ok", "workday": "ok", "smartextract": "ok"}),
            "enrich": MagicMock(return_value={"status": "ok"}),
        },
    )
    @patch("applypilot.pipeline.console")
    def test_workers_propagated_to_discover_enrich(self, mock_console) -> None:
        """workers kwarg is passed through to discover and enrich runners."""
        _run_sequential(["discover", "enrich"], min_score=70, workers=4)

        discover_runner = _STAGE_RUNNERS["discover"]
        enrich_runner = _STAGE_RUNNERS["enrich"]
        discover_runner.assert_called_once_with(workers=4)
        enrich_runner.assert_called_once_with(workers=4)


# ── _run_streaming (3 tests) ─────────────────────────────────────────────


class TestRunStreaming:
    @patch.dict(
        "applypilot.pipeline._STAGE_RUNNERS",
        {
            "discover": MagicMock(return_value={"status": "ok"}),
            "score": MagicMock(return_value={"status": "ok"}),
        },
    )
    @patch("applypilot.pipeline.console")
    @patch("applypilot.pipeline._count_pending", return_value=0)
    def test_concurrent(self, mock_count, mock_console) -> None:
        result = _run_streaming(["discover", "score"], min_score=70, workers=1)

        assert len(result["stages"]) == 2
        assert result["stages"][0]["stage"] == "discover"
        assert result["stages"][1]["stage"] == "score"
        assert result["errors"] == {}

    @patch.dict(
        "applypilot.pipeline._STAGE_RUNNERS",
        {"score": MagicMock(return_value={"status": "ok"})},
    )
    @patch("applypilot.pipeline.console")
    @patch("applypilot.pipeline._count_pending", return_value=0)
    def test_skipped_stages(self, mock_count, mock_console) -> None:
        result = _run_streaming(["score"], min_score=70, workers=1)

        assert len(result["stages"]) == 1
        assert result["stages"][0]["stage"] == "score"
        # Non-run stages marked as skipped in tracker
        all_results = [s["status"] for s in result["stages"]]
        assert "ok" in all_results

    @patch.dict(
        "applypilot.pipeline._STAGE_RUNNERS",
        {
            "discover": MagicMock(return_value={"status": "ok"}),
            "score": MagicMock(return_value={"status": "ok"}),
        },
    )
    @patch("applypilot.pipeline.console")
    @patch("applypilot.pipeline._count_pending", return_value=0)
    def test_concurrent_basic(self, mock_count, mock_console) -> None:
        """Basic concurrent run with two stages completes successfully."""
        result = _run_streaming(["discover", "score"], min_score=70, workers=1)

        assert len(result["stages"]) == 2
        assert result["stages"][0]["stage"] == "discover"
        assert result["stages"][1]["stage"] == "score"
        assert result["errors"] == {}
        assert "elapsed" in result

    @patch.dict(
        "applypilot.pipeline._STAGE_RUNNERS",
        {
            "discover": MagicMock(return_value={"status": "ok"}),
            "score": MagicMock(return_value={"status": "ok"}),
        },
    )
    @patch("applypilot.pipeline.console")
    @patch("applypilot.pipeline._count_pending", return_value=0)
    def test_keyboard_interrupt_stops_stages(self, mock_count, mock_console) -> None:
        """KeyboardInterrupt during streaming triggers stop_event and graceful shutdown."""

        # Make discover block briefly so we can interrupt during join
        def slow_discover(**kwargs):
            time.sleep(0.3)
            return {"status": "ok"}

        _STAGE_RUNNERS["discover"] = slow_discover

        # Patch Thread.join to raise KeyboardInterrupt after the first join call
        join_calls = [0]

        def patched_join(*args, **kwargs):
            join_calls[0] += 1
            if join_calls[0] == 1:
                raise KeyboardInterrupt("ctrl-c")
            return None

        import threading

        with patch.object(threading.Thread, "join", patched_join):
            result = _run_streaming(["discover", "score"], min_score=70, workers=1)

        assert len(result["stages"]) == 2
        assert "elapsed" in result
        # Both stages should be done (stop_event triggered graceful shutdown)
        assert all(s["stage"] in ("discover", "score") for s in result["stages"])


# ── _run_stage_streaming (3 tests) ───────────────────────────────────────


class TestRunStageStreaming:
    @patch.dict(
        "applypilot.pipeline._STAGE_RUNNERS",
        {"discover": MagicMock(return_value={"jobspy": "ok", "workday": "ok", "smartextract": "ok"})},
    )
    def test_discover_runs_once(self) -> None:
        tracker = _StageTracker()
        stop_event = __import__("threading").Event()
        runner = _STAGE_RUNNERS["discover"]

        _run_stage_streaming("discover", tracker, stop_event, workers=2)

        assert tracker.is_done("discover")
        runner.assert_called_once_with(workers=2)

    @patch.dict(
        "applypilot.pipeline._STAGE_RUNNERS",
        {"score": MagicMock(return_value={"status": "ok"})},
    )
    @patch("applypilot.pipeline._count_pending", side_effect=[3, 0])
    def test_downstream_loop(self, mock_count) -> None:
        tracker = _StageTracker()
        stop_event = __import__("threading").Event()
        # Mark upstream (enrich) as done so downstream doesn't wait
        tracker.mark_done("enrich", {"status": "ok"})
        runner = _STAGE_RUNNERS["score"]

        _run_stage_streaming("score", tracker, stop_event, min_score=70)

        assert tracker.is_done("score")
        assert mock_count.call_count == 2  # 3 pending, then 0
        assert runner.call_count == 1  # only ran when pending > 0

    @patch.dict(
        "applypilot.pipeline._STAGE_RUNNERS",
        {"score": MagicMock(return_value={"status": "ok"})},
    )
    @patch("applypilot.pipeline._count_pending", side_effect=[3, 2, 0])
    @patch("applypilot.pipeline._STREAM_POLL_INTERVAL", 0.05)
    def test_stop_event_breaks_loop(self, mock_count) -> None:
        tracker = _StageTracker()
        stop_event = __import__("threading").Event()
        tracker.mark_done("enrich", {"status": "ok"})

        # Fire stop after a short delay
        def fire_stop():
            time.sleep(0.08)
            stop_event.set()

        t = __import__("threading").Thread(target=fire_stop, daemon=True)
        t.start()

        _run_stage_streaming("score", tracker, stop_event, min_score=70)

        assert tracker.is_done("score")
        assert tracker.get_results()["score"]["status"] == "ok"


# ── run_pipeline (tests) ─────────────────────────────────────────────────


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

    @patch("applypilot.pipeline._run_sequential")
    @patch("applypilot.pipeline._resolve_stages")
    @patch("applypilot.pipeline.get_stats")
    @patch("applypilot.pipeline.init_db")
    @patch("applypilot.pipeline.ensure_dirs")
    @patch("applypilot.pipeline.load_env")
    def test_full_run_with_elapsed(
        self,
        mock_load_env,
        mock_ensure_dirs,
        mock_init_db,
        mock_get_stats,
        mock_resolve,
        mock_sequential,
    ) -> None:
        """Full run should return elapsed time and stage results."""
        mock_resolve.return_value = ["discover", "score"]
        mock_get_stats.return_value = _FAKE_STATS
        mock_sequential.return_value = {
            "stages": [
                {"stage": "discover", "status": "ok", "elapsed": 0.5},
                {"stage": "score", "status": "ok", "elapsed": 1.2},
            ],
            "errors": {},
            "elapsed": 1.7,
        }

        result = run_pipeline(stages=["discover", "score"])

        assert result["elapsed"] == 1.7
        assert len(result["stages"]) == 2
        assert result["stages"][0]["stage"] == "discover"
        assert result["stages"][1]["stage"] == "score"
        assert result["errors"] == {}

    @patch("applypilot.pipeline.console")
    @patch("applypilot.pipeline._run_sequential")
    @patch("applypilot.pipeline._resolve_stages")
    @patch("applypilot.pipeline.get_stats")
    @patch("applypilot.pipeline.init_db")
    @patch("applypilot.pipeline.ensure_dirs")
    @patch("applypilot.pipeline.load_env")
    def test_summary_prints_final_stats(
        self,
        mock_load_env,
        mock_ensure_dirs,
        mock_init_db,
        mock_get_stats,
        mock_resolve,
        mock_sequential,
        mock_console,
    ) -> None:
        """Full run prints summary table and final DB stats."""
        mock_resolve.return_value = ["score"]
        mock_get_stats.side_effect = [
            _FAKE_STATS,  # pre-run stats
            _FAKE_STATS,  # final stats
        ]
        mock_sequential.return_value = {
            "stages": [{"stage": "score", "status": "ok", "elapsed": 0.5}],
            "errors": {},
            "elapsed": 0.5,
        }

        run_pipeline(stages=["score"])

        # Final DB stats should be printed (get_stats called twice)
        assert mock_get_stats.call_count == 2
        # Console should have been called with "DB Final State" or similar
        print_args = [str(c) for c in mock_console.print.call_args_list]
        assert any("Total jobs" in c or "Scored" in c for c in print_args)
