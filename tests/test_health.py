"""Tests for health monitoring — health.json, --health, --watchdog, source tracking."""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from services.health_tracker import HealthTracker

# ──────────────── Fixtures ────────────────


@pytest.fixture
def health_file(tmp_path):
    return tmp_path / "health.json"


@pytest.fixture
def tracker(health_file):
    return HealthTracker(health_file)


def _write_health(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def _make_health(
    status: str = "ok",
    last_run: str | None = None,
    minutes_ago: int = 5,
    profile_results: dict | None = None,
    sources_health: dict | None = None,
) -> dict:
    if last_run is None:
        last_run = (datetime.now() - timedelta(minutes=minutes_ago)).isoformat(timespec="seconds")
    return {
        "last_run": last_run,
        "status": status,
        "duration_seconds": 12.3,
        "version": "0.1.0",
        "profile_results": profile_results or {},
        "sources_health": sources_health or {},
    }


# ──────────────── health.json read/write ────────────────


class TestLoadSaveHealth:
    def test_load_missing_returns_none(self, tracker):
        assert tracker.load() is None

    def test_save_and_load(self, tracker):
        data = _make_health()
        tracker.save(data)
        loaded = tracker.load()
        assert loaded is not None
        assert loaded["status"] == "ok"
        assert loaded["version"] == "0.1.0"

    def test_load_corrupt_returns_none(self, tracker, health_file):
        health_file.write_text("not json {{{")
        assert tracker.load() is None

    def test_save_creates_parent_dir(self, tmp_path):
        nested = tmp_path / "sub" / "health.json"
        t = HealthTracker(nested)
        t.save(_make_health())
        assert nested.exists()


# ──────────────── _compute_status ────────────────


class TestComputeOverallStatus:
    def test_all_ok(self):
        results = {
            "bikes": {"status": "ok"},
            "nas": {"status": "ok"},
        }
        assert HealthTracker._compute_status(results) == "ok"

    def test_all_error(self):
        results = {
            "bikes": {"status": "error"},
            "nas": {"status": "error"},
        }
        assert HealthTracker._compute_status(results) == "error"

    def test_partial(self):
        results = {
            "bikes": {"status": "ok"},
            "nas": {"status": "error"},
        }
        assert HealthTracker._compute_status(results) == "partial"

    def test_empty_profiles_is_error(self):
        assert HealthTracker._compute_status({}) == "error"


# ──────────────── update_sources ────────────────


class TestUpdateSourcesHealth:
    def test_first_run_all_success(self, tracker):
        result = tracker.update_sources(None, {"pepper": True, "ceneo": True})
        assert result["pepper"]["status"] == "ok"
        assert result["pepper"]["consecutive_failures"] == 0
        assert result["ceneo"]["status"] == "ok"

    def test_first_run_failure(self, tracker):
        result = tracker.update_sources(None, {"pepper": False})
        assert result["pepper"]["status"] == "degraded"
        assert result["pepper"]["consecutive_failures"] == 1

    def test_consecutive_failures_increment(self, tracker):
        existing = _make_health(
            sources_health={
                "pepper": {
                    "status": "degraded",
                    "last_success": "2026-04-01T10:00:00",
                    "consecutive_failures": 2,
                },
            }
        )
        result = tracker.update_sources(existing, {"pepper": False})
        assert result["pepper"]["consecutive_failures"] == 3
        assert result["pepper"]["status"] == "down"
        assert result["pepper"]["last_success"] == "2026-04-01T10:00:00"

    def test_success_resets_failures(self, tracker):
        existing = _make_health(
            sources_health={
                "pepper": {
                    "status": "down",
                    "last_success": "2026-04-01T10:00:00",
                    "consecutive_failures": 5,
                },
            }
        )
        result = tracker.update_sources(existing, {"pepper": True})
        assert result["pepper"]["consecutive_failures"] == 0
        assert result["pepper"]["status"] == "ok"

    def test_preserves_unseen_sources(self, tracker):
        existing = _make_health(
            sources_health={
                "canyon": {
                    "status": "ok",
                    "last_success": "2026-04-01T10:00:00",
                    "consecutive_failures": 0,
                },
            }
        )
        result = tracker.update_sources(existing, {"pepper": True})
        assert "canyon" in result
        assert result["canyon"]["status"] == "ok"


# ──────────────── build_data ────────────────


class TestBuildHealthData:
    def test_builds_complete_structure(self, tracker):
        profiles = {"bikes": {"status": "ok", "deals_found": 10, "new_alerts": 2, "errors": []}}
        sources = {"pepper": {"status": "ok", "last_success": "...", "consecutive_failures": 0}}
        data = tracker.build_data(profiles, sources, 45.2, "0.1.0")

        assert "last_run" in data
        assert data["status"] == "ok"
        assert data["duration_seconds"] == 45.2
        assert data["version"] == "0.1.0"
        assert data["profile_results"] == profiles
        assert data["sources_health"] == sources


# ──────────────── get_failing_sources ────────────────


class TestGetFailingSources:
    def test_no_failures(self):
        sources = {"pepper": {"consecutive_failures": 0}, "ceneo": {"consecutive_failures": 2}}
        assert HealthTracker.get_failing_sources(sources) == []

    def test_returns_failing(self):
        sources = {
            "pepper": {"consecutive_failures": 3},
            "ceneo": {"consecutive_failures": 0},
            "canyon": {"consecutive_failures": 5},
        }
        result = HealthTracker.get_failing_sources(sources)
        assert "pepper" in result
        assert "canyon" in result
        assert "ceneo" not in result


# ──────────────── print_status (--health CLI) ────────────────


class TestPrintHealthStatus:
    def test_no_health_file(self, tracker, capsys):
        exit_code = tracker.print_status()
        assert exit_code == 3
        assert "No health data" in capsys.readouterr().out

    def test_stale_health(self, tracker, health_file, capsys):
        data = _make_health(minutes_ago=180)
        _write_health(health_file, data)
        exit_code = tracker.print_status()
        assert exit_code == 3
        assert "STALE" in capsys.readouterr().out

    def test_ok_status(self, tracker, health_file, capsys):
        data = _make_health(
            status="ok",
            minutes_ago=5,
            profile_results={
                "bikes": {"status": "ok", "deals_found": 100, "new_alerts": 2, "errors": []}
            },
            sources_health={"pepper": {"status": "ok", "consecutive_failures": 0}},
        )
        _write_health(health_file, data)
        exit_code = tracker.print_status()
        captured = capsys.readouterr().out
        assert exit_code == 0
        assert "OK" in captured
        assert "bikes" in captured
        assert "pepper" in captured

    def test_partial_status(self, tracker, health_file, capsys):
        data = _make_health(
            status="partial",
            minutes_ago=10,
            profile_results={
                "bikes": {"status": "ok", "deals_found": 50, "new_alerts": 1, "errors": []},
                "nas": {
                    "status": "error",
                    "deals_found": 0,
                    "new_alerts": 0,
                    "errors": ["Pepper timeout"],
                },
            },
        )
        _write_health(health_file, data)
        exit_code = tracker.print_status()
        captured = capsys.readouterr().out
        assert exit_code == 1
        assert "PARTIAL" in captured
        assert "Pepper timeout" in captured

    def test_error_status(self, tracker, health_file, capsys):
        data = _make_health(status="error", minutes_ago=10)
        _write_health(health_file, data)
        exit_code = tracker.print_status()
        assert exit_code == 2

    def test_degraded_source_shown(self, tracker, health_file, capsys):
        data = _make_health(
            sources_health={"canyon": {"status": "degraded", "consecutive_failures": 2}},
        )
        _write_health(health_file, data)
        tracker.print_status()
        captured = capsys.readouterr().out
        assert "consecutive failures: 2" in captured


# ──────────────── check_watchdog (--watchdog CLI) ────────────────


class TestCheckWatchdog:
    def test_no_health_file(self, tracker):
        ok, msg = tracker.check_watchdog()
        assert not ok
        assert "never run" in msg

    def test_fresh_run(self, tracker, health_file):
        _write_health(health_file, _make_health(minutes_ago=30))
        ok, msg = tracker.check_watchdog()
        assert ok
        assert msg == "OK"

    def test_stale_run(self, tracker, health_file):
        _write_health(health_file, _make_health(minutes_ago=180))
        ok, msg = tracker.check_watchdog()
        assert not ok
        assert "ago" in msg
        assert "Check cron" in msg

    def test_invalid_timestamp(self, tracker, health_file):
        data = _make_health()
        data["last_run"] = "not-a-date"
        _write_health(health_file, data)
        ok, msg = tracker.check_watchdog()
        assert not ok
        assert "invalid" in msg


# ──────────────── _format_timedelta ────────────────


class TestFormatTimedelta:
    def test_seconds(self):
        assert HealthTracker._format_timedelta(timedelta(seconds=45)) == "45s"

    def test_minutes(self):
        assert HealthTracker._format_timedelta(timedelta(minutes=15)) == "15m"

    def test_hours(self):
        assert HealthTracker._format_timedelta(timedelta(hours=3, minutes=15)) == "3h 15m"

    def test_hours_exact(self):
        assert HealthTracker._format_timedelta(timedelta(hours=2)) == "2h"

    def test_days(self):
        assert HealthTracker._format_timedelta(timedelta(days=2, hours=5)) == "2d 5h"
