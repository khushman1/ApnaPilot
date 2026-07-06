"""Tests for applypilot.database: schema, queries, stats, migrations."""

from __future__ import annotations

import sqlite3


from applypilot import database
from applypilot.database import get_connection, get_jobs_by_stage, init_db, store_jobs


class TestInitDb:
    def test_creates_jobs_table(self, tmp_path) -> None:
        db_path = tmp_path / "test.db"
        conn = init_db(db_path=str(db_path))
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'").fetchall()
        assert len(tables) == 1

    def test_creates_app_meta_table(self, tmp_path) -> None:
        db_path = tmp_path / "test.db"
        conn = init_db(db_path=str(db_path))
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='app_meta'").fetchall()
        assert len(tables) == 1

    def test_idempotent_safe_to_call_twice(self, tmp_path) -> None:
        db_path = tmp_path / "test.db"
        conn1 = init_db(db_path=str(db_path))
        conn2 = init_db(db_path=str(db_path))
        # Both connections should work fine
        assert conn1.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0
        assert conn2.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0

    def test_creates_parent_directory(self, tmp_path) -> None:
        db_path = tmp_path / "sub" / "deep" / "test.db"
        conn = init_db(db_path=str(db_path))
        assert db_path.parent.is_dir()
        assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0


class TestGetConnection:
    def test_returns_same_connection_per_thread(self, tmp_path) -> None:
        db_path = tmp_path / "test.db"
        init_db(db_path=str(db_path))
        c1 = get_connection(db_path)
        c2 = get_connection(db_path)
        assert c1 is c2

    def test_different_paths_yield_different_connections(self, tmp_path) -> None:
        p1 = tmp_path / "test1.db"
        p2 = tmp_path / "test2.db"
        init_db(db_path=str(p1))
        init_db(db_path=str(p2))
        c1 = get_connection(p1)
        c2 = get_connection(p2)
        assert c1 is not c2

    def test_closes_and_reconnects(self, tmp_path) -> None:
        db_path = tmp_path / "test.db"
        conn = init_db(db_path=str(db_path))
        database.close_connection(db_path)
        # After close, next get_connection should create a new one
        new_conn = get_connection(db_path)
        assert new_conn is not conn
        # Should still work
        new_conn.execute("SELECT 1")

    def test_wal_mode_enabled(self, tmp_path) -> None:
        db_path = tmp_path / "test.db"
        conn = init_db(db_path=str(db_path))
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"

    def test_row_factory_is_row(self, tmp_path) -> None:
        db_path = tmp_path / "test.db"
        conn = init_db(db_path=str(db_path))
        conn.execute("INSERT INTO jobs(url, title) VALUES (?, ?)", ("https://x.com/j", "Test"))
        conn.commit()
        row = conn.execute("SELECT url, title FROM jobs WHERE url = ?", ("https://x.com/j",)).fetchone()
        assert isinstance(row, sqlite3.Row)
        assert row["url"] == "https://x.com/j"


class TestStoreJobs:
    def test_inserts_new_jobs(self, tmp_path) -> None:
        db_path = tmp_path / "test.db"
        conn = init_db(db_path=str(db_path))
        jobs = [
            {"url": "https://example.com/1", "title": "Job 1"},
            {"url": "https://example.com/2", "title": "Job 2"},
        ]
        new_count, dup_count = store_jobs(conn, jobs, "RemoteOK", "json_ld")
        assert new_count == 2
        assert dup_count == 0

    def test_skips_duplicates(self, tmp_path) -> None:
        db_path = tmp_path / "test.db"
        conn = init_db(db_path=str(db_path))
        jobs = [
            {"url": "https://example.com/1", "title": "Job 1"},
            {"url": "https://example.com/2", "title": "Job 2"},
        ]
        store_jobs(conn, jobs, "RemoteOK", "json_ld")
        new_count, dup_count = store_jobs(conn, jobs, "RemoteOK", "json_ld")
        assert new_count == 0
        assert dup_count == 2

    def test_skips_jobs_without_url(self, tmp_path) -> None:
        db_path = tmp_path / "test.db"
        conn = init_db(db_path=str(db_path))
        jobs = [
            {"url": "https://example.com/1", "title": "Job 1"},
            {"title": "No URL Job"},
        ]
        new_count, _ = store_jobs(conn, jobs, "RemoteOK", "json_ld")
        assert new_count == 1


class TestGetJobsByStage:
    def test_discovered_returns_all(self, tmp_path) -> None:
        db_path = tmp_path / "test.db"
        conn = init_db(db_path=str(db_path))
        conn.execute(
            "INSERT INTO jobs(url, title, fit_score) VALUES (?, ?, ?)",
            ("https://example.com/1", "Job 1", 80),
        )
        conn.commit()
        jobs = get_jobs_by_stage(conn=conn, stage="discovered", limit=10)
        assert len(jobs) == 1
        assert jobs[0]["title"] == "Job 1"

    def test_pending_detail_filters_no_description(self, tmp_path) -> None:
        db_path = tmp_path / "test.db"
        conn = init_db(db_path=str(db_path))
        conn.execute(
            "INSERT INTO jobs(url, title, full_description, detail_scraped_at) VALUES (?, ?, ?, ?)",
            ("https://example.com/1", "Job 1", None, None),
        )
        conn.execute(
            "INSERT INTO jobs(url, title, full_description, detail_scraped_at) VALUES (?, ?, ?, ?)",
            ("https://example.com/2", "Job 2", "desc", "2024-01-01T00:00:00"),
        )
        conn.commit()
        jobs = get_jobs_by_stage(conn=conn, stage="pending_detail", limit=10)
        assert len(jobs) == 1
        assert jobs[0]["title"] == "Job 1"

    def test_scored_filters_by_fit_score(self, tmp_path) -> None:
        db_path = tmp_path / "test.db"
        conn = init_db(db_path=str(db_path))
        conn.execute(
            "INSERT INTO jobs(url, title, fit_score) VALUES (?, ?, ?)",
            ("https://example.com/1", "Low", 50),
        )
        conn.execute(
            "INSERT INTO jobs(url, title, fit_score) VALUES (?, ?, ?)",
            ("https://example.com/2", "High", 85),
        )
        conn.commit()
        jobs = get_jobs_by_stage(conn=conn, stage="scored", min_score=70, limit=10)
        assert len(jobs) == 1
        assert jobs[0]["title"] == "High"

    def test_empty_table_returns_empty_list(self, tmp_path) -> None:
        db_path = tmp_path / "test.db"
        conn = init_db(db_path=str(db_path))
        jobs = get_jobs_by_stage(conn=conn, stage="discovered")
        assert jobs == []

    def test_limit_respected(self, tmp_path) -> None:
        db_path = tmp_path / "test.db"
        conn = init_db(db_path=str(db_path))
        for i in range(5):
            conn.execute(
                "INSERT INTO jobs(url, title) VALUES (?, ?)",
                (f"https://example.com/{i}", f"Job {i}"),
            )
        conn.commit()
        jobs = get_jobs_by_stage(conn=conn, stage="discovered", limit=3)
        assert len(jobs) == 3

    def test_returns_dicts(self, tmp_path) -> None:
        db_path = tmp_path / "test.db"
        conn = init_db(db_path=str(db_path))
        conn.execute(
            "INSERT INTO jobs(url, title) VALUES (?, ?)",
            ("https://example.com/1", "Job 1"),
        )
        conn.commit()
        jobs = get_jobs_by_stage(conn=conn, stage="discovered", limit=10)
        assert isinstance(jobs[0], dict)
        assert "url" in jobs[0]
        assert "title" in jobs[0]


class TestGetStats:
    def test_empty_db_returns_zero_totals(self, tmp_path) -> None:
        db_path = tmp_path / "test.db"
        conn = init_db(db_path=str(db_path))
        stats = database.get_stats(conn=conn)
        assert stats["total"] == 0
        assert stats["scored"] == 0
        assert stats["tailored"] == 0
        assert stats["applied"] == 0

    def test_counts_by_stage(self, tmp_path) -> None:
        db_path = tmp_path / "test.db"
        conn = init_db(db_path=str(db_path))
        # Job with description but no score
        conn.execute(
            "INSERT INTO jobs(url, title, full_description) VALUES (?, ?, ?)",
            ("https://example.com/1", "Job 1", "desc"),
        )
        # Scored job
        conn.execute(
            "INSERT INTO jobs(url, title, full_description, fit_score) VALUES (?, ?, ?, ?)",
            ("https://example.com/2", "Job 2", "desc", 80),
        )
        # Tailored job
        conn.execute(
            "INSERT INTO jobs(url, title, full_description, fit_score, tailored_resume_path) VALUES (?, ?, ?, ?, ?)",
            ("https://example.com/3", "Job 3", "desc", 85, "/path/to/resume.txt"),
        )
        conn.commit()

        stats = database.get_stats(conn=conn)
        assert stats["total"] == 3
        assert stats["with_description"] == 3
        assert stats["scored"] == 2
        assert stats["unscored"] == 1
        assert stats["tailored"] == 1

    def test_by_site_breakdown(self, tmp_path) -> None:
        db_path = tmp_path / "test.db"
        conn = init_db(db_path=str(db_path))
        conn.execute(
            "INSERT INTO jobs(url, title, site) VALUES (?, ?, ?)",
            ("https://example.com/1", "Job 1", "LinkedIn"),
        )
        conn.execute(
            "INSERT INTO jobs(url, title, site) VALUES (?, ?, ?)",
            ("https://example.com/2", "Job 2", "LinkedIn"),
        )
        conn.execute(
            "INSERT INTO jobs(url, title, site) VALUES (?, ?, ?)",
            ("https://example.com/3", "Job 3", "Dice"),
        )
        conn.commit()

        stats = database.get_stats(conn=conn)
        by_site = {site: count for site, count in stats["by_site"]}
        assert by_site.get("LinkedIn") == 2
        assert by_site.get("Dice") == 1

    def test_score_buckets(self, tmp_path) -> None:
        db_path = tmp_path / "test.db"
        conn = init_db(db_path=str(db_path))
        conn.execute(
            "INSERT INTO jobs(url, title, fit_score) VALUES (?, ?, ?)",
            ("https://example.com/1", "Low", 55),
        )
        conn.execute(
            "INSERT INTO jobs(url, title, fit_score) VALUES (?, ?, ?)",
            ("https://example.com/2", "Mid", 78),
        )
        conn.execute(
            "INSERT INTO jobs(url, title, fit_score) VALUES (?, ?, ?)",
            ("https://example.com/3", "High", 92),
        )
        conn.commit()

        stats = database.get_stats(conn=conn)
        buckets = {name: count for name, count in stats["score_buckets"]}
        assert buckets["Human review (90+)"] == 1
        assert buckets["Auto-eligible (70-89)"] == 1
        assert buckets["Skip (<70)"] == 1


class TestEnsureColumns:
    def test_returns_empty_when_schema_current(self, tmp_path) -> None:
        db_path = tmp_path / "test.db"
        conn = init_db(db_path=str(db_path))
        added = database.ensure_columns(conn)
        assert added == []

    def test_adds_missing_columns(self, tmp_path) -> None:
        db_path = tmp_path / "test.db"
        # Create a bare table with only the url column
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE jobs (
                url TEXT PRIMARY KEY,
                title TEXT
            )
        """)
        conn.execute("CREATE TABLE app_meta (key TEXT PRIMARY KEY, value TEXT)")
        conn.commit()

        # Run ensure_columns directly (init_db would do it too, but we want
        # to capture the returned list)
        added = database.ensure_columns(conn)
        assert len(added) > 0
        assert "fit_score" in added or "full_description" in added
        conn.close()


class TestCloseConnection:
    def test_closes_existing_connection(self, tmp_path) -> None:
        db_path = tmp_path / "test.db"
        conn = init_db(db_path=str(db_path))
        database.close_connection(db_path)
        # After close, get_connection should return a new connection
        new_conn = get_connection(db_path)
        assert new_conn is not conn
        # Should work fine
        new_conn.execute("SELECT 1")
