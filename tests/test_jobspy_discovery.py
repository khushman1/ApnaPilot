from __future__ import annotations

import sys
import types
import importlib

import pandas as pd

from applypilot.discovery.location_filter import load_location_filter, location_ok


def _import_jobspy_module(monkeypatch):
    fake_jobspy = types.ModuleType("jobspy")
    fake_jobspy.scrape_jobs = lambda **kwargs: pd.DataFrame()
    monkeypatch.setitem(sys.modules, "jobspy", fake_jobspy)
    monkeypatch.delitem(sys.modules, "applypilot.discovery.jobspy", raising=False)

    return importlib.import_module("applypilot.discovery.jobspy")


def test_run_discovery_uses_boards_key(monkeypatch) -> None:
    jobspy = _import_jobspy_module(monkeypatch)
    captured: dict = {}

    def fake_full_crawl(**kwargs):
        captured.update(kwargs)
        return {"new": 0, "existing": 0, "errors": 0, "db_total": 0, "queries": 0}

    monkeypatch.setattr(jobspy, "_full_crawl", fake_full_crawl)

    result = jobspy.run_discovery({
        "boards": ["indeed", "linkedin"],
        "queries": [{"query": "Product Manager", "tier": 1}],
        "locations": [{"location": "Remote", "remote": True}],
        "defaults": {"results_per_site": 10, "hours_old": 24},
    })

    assert result["queries"] == 0
    assert captured["sites"] == ["indeed", "linkedin"]


def test_run_one_search_continues_when_one_board_fails(monkeypatch) -> None:
    jobspy = _import_jobspy_module(monkeypatch)
    calls: list[str] = []

    def fake_scrape_jobs(**kwargs):
        site = kwargs["site_name"][0]
        calls.append(site)
        if site == "zip_recruiter":
            raise RuntimeError("ZipRecruiter response status code 403")
        return pd.DataFrame([{
            "job_url": "https://example.com/job",
            "title": "Product Manager",
            "company": "Example",
            "location": "Remote",
            "description": "A detailed remote product manager role." * 20,
            "site": site,
            "is_remote": True,
        }])

    stored: dict = {}

    def fake_store_results(conn, df, source_label):
        stored["rows"] = len(df)
        stored["source_label"] = source_label
        return len(df), 0

    monkeypatch.setattr(jobspy, "scrape_jobs", fake_scrape_jobs)
    monkeypatch.setattr(jobspy, "get_connection", lambda: object())
    monkeypatch.setattr(jobspy, "store_jobspy_results", fake_store_results)

    result = jobspy._run_one_search(
        search={"query": "Product Manager", "location": "Remote", "remote": True, "tier": 1},
        sites=["indeed", "zip_recruiter"],
        results_per_site=10,
        hours_old=24,
        proxy_config=None,
        defaults={},
        max_retries=0,
        location_filter=load_location_filter({"location": {"accept_patterns": ["Remote"], "remote_anywhere": True}}),
        glassdoor_map={},
    )

    assert calls == ["indeed", "zip_recruiter"]
    assert stored == {"rows": 1, "source_label": "Product Manager"}
    assert result["new"] == 1
    assert result["errors"] == 0


def test_location_filter_derives_india_locations_and_blocks_other_remote_regions() -> None:
    filt = load_location_filter({
        "locations": [
            {"location": "Bengaluru, Karnataka, India", "remote": True},
            {"location": "Gurugram, Haryana, India", "remote": True},
            {"location": "APAC", "remote": True},
        ]
    })

    assert location_ok("Bengaluru, Karnataka, India", filt) is True
    assert location_ok("Remote - India", filt) is True
    assert location_ok("APAC Remote", filt) is True
    assert location_ok("Remote - United States", filt) is False
    assert location_ok("London, UK", filt) is False


def test_location_filter_can_explicitly_allow_worldwide_remote() -> None:
    filt = load_location_filter({
        "location": {
            "accept_patterns": ["India"],
            "remote_anywhere": True,
        }
    })

    assert location_ok("Remote - United States", filt) is True
