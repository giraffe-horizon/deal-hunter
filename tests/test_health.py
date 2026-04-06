"""Tests for health monitoring — health.json, --health, --watchdog, source tracking."""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import health

# ──────────────── Fixtures ────────────────


@pytest.fixture(autouse=True)
def use_tmp_health_file(tmp_path):
    """Redirect HEALTH_FILE to tmp_path for all tests."""
    health_file = tmp_path / "health.json"
    with patch.object(health, "HEALTH_FILE", health_file):
        yield health_file


def _write_health(path: Path, data: dict) -> None:
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
    def test_load_missing_returns_none(self):
        assert health.load_health() is None

    def test_save_and_load(self, use_tmp_health_file):
        data = _make_health()
        health.save_health(data)
        loaded = health.load_health()
        assert loaded is not None
        assert loaded["status"] == "ok"
        assert loaded["version"] == "0.1.0"

    def test_load_corrupt_returns_none(self, use_tmp_health_file):
        use_tmp_health_file.write_text("not json {{{")
        assert health.load_health() is None

    def test_save_creates_parent_dir(self, tmp_path):
        nested = tmp_path / "sub" / "health.json"
        with patch.object(health, "HEALTH_FILE", nested):
            health.save_health(_make_health())
        assert nested.exists()


# ──────────────── compute_overall_status ────────────────


class TestComputeOverallStatus:
    def test_all_ok(self):
        results = {
            "bikes": {"status": "ok"},
            "nas": {"status": "ok"},
        }
        assert health.compute_overall_status(results) == "ok"

    def test_all_error(self):
        results = {
            "bikes": {"status": "error"},
            "nas": {"status": "error"},
        }
        assert health.compute_overall_status(results) == "error"

    def test_partial(self):
        results = {
            "bikes": {"status": "ok"},
            "nas": {"status": "error"},
        }
        assert health.compute_overall_status(results) == "partial"

    def test_empty_profiles_is_error(self):
        assert health.compute_overall_status({}) == "error"


# ──────────────── update_sources_health ────────────────


class TestUpdateSourcesHealth:
    def test_first_run_all_success(self):
        result = health.update_sources_health(None, {"pepper": True, "ceneo": True})
        assert result["pepper"]["status"] == "ok"
        assert result["pepper"]["consecutive_failures"] == 0
        assert result["ceneo"]["status"] == "ok"

    def test_first_run_failure(self):
        result = health.update_sources_health(None, {"pepper": False})
        assert result["pepper"]["status"] == "degraded"
        assert result["pepper"]["consecutive_failures"] == 1

    def test_consecutive_failures_increment(self):
        existing = _make_health(
            sources_health={
                "pepper": {
                    "status": "degraded",
                    "last_success": "2026-04-01T10:00:00",
                    "consecutive_failures": 2,
                },
            }
        )
        result = health.update_sources_health(existing, {"pepper": False})
        assert result["pepper"]["consecutive_failures"] == 3
        assert result["pepper"]["status"] == "down"
        assert result["pepper"]["last_success"] == "2026-04-01T10:00:00"

    def test_success_resets_failures(self):
        existing = _make_health(
            sources_health={
                "pepper": {
                    "status": "down",
                    "last_success": "2026-04-01T10:00:00",
                    "consecutive_failures": 5,
                },
            }
        )
        result = health.update_sources_health(existing, {"pepper": True})
        assert result["pepper"]["consecutive_failures"] == 0
        assert result["pepper"]["status"] == "ok"

    def test_preserves_unseen_sources(self):
        existing = _make_health(
            sources_health={
                "canyon": {
                    "status": "ok",
                    "last_success": "2026-04-01T10:00:00",
                    "consecutive_failures": 0,
                },
            }
        )
        result = health.update_sources_health(existing, {"pepper": True})
        assert "canyon" in result
        assert result["canyon"]["status"] == "ok"


# ──────────────── build_health_data ────────────────


class TestBuildHealthData:
    def test_builds_complete_structure(self):
        profiles = {"bikes": {"status": "ok", "deals_found": 10, "new_alerts": 2, "errors": []}}
        sources = {"pepper": {"status": "ok", "last_success": "...", "consecutive_failures": 0}}
        data = health.build_health_data(profiles, sources, 45.2, "0.1.0")

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
        assert health.get_failing_sources(sources) == []

    def test_returns_failing(self):
        sources = {
            "pepper": {"consecutive_failures": 3},
            "ceneo": {"consecutive_failures": 0},
            "canyon": {"consecutive_failures": 5},
        }
        result = health.get_failing_sources(sources)
        assert "pepper" in result
        assert "canyon" in result
        assert "ceneo" not in result


# ──────────────── --health CLI ────────────────


class TestPrintHealthStatus:
    def test_no_health_file(self, capsys):
        exit_code = health.print_health_status()
        assert exit_code == 3
        assert "No health data" in capsys.readouterr().out

    def test_stale_health(self, use_tmp_health_file, capsys):
        data = _make_health(minutes_ago=180)
        _write_health(use_tmp_health_file, data)
        exit_code = health.print_health_status()
        assert exit_code == 3
        assert "STALE" in capsys.readouterr().out

    def test_ok_status(self, use_tmp_health_file, capsys):
        data = _make_health(
            status="ok",
            minutes_ago=5,
            profile_results={
                "bikes": {"status": "ok", "deals_found": 100, "new_alerts": 2, "errors": []}
            },
            sources_health={"pepper": {"status": "ok", "consecutive_failures": 0}},
        )
        _write_health(use_tmp_health_file, data)
        exit_code = health.print_health_status()
        captured = capsys.readouterr().out
        assert exit_code == 0
        assert "OK" in captured
        assert "bikes" in captured
        assert "pepper" in captured

    def test_partial_status(self, use_tmp_health_file, capsys):
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
        _write_health(use_tmp_health_file, data)
        exit_code = health.print_health_status()
        captured = capsys.readouterr().out
        assert exit_code == 1
        assert "PARTIAL" in captured
        assert "Pepper timeout" in captured

    def test_error_status(self, use_tmp_health_file, capsys):
        data = _make_health(status="error", minutes_ago=10)
        _write_health(use_tmp_health_file, data)
        exit_code = health.print_health_status()
        assert exit_code == 2

    def test_degraded_source_shown(self, use_tmp_health_file, capsys):
        data = _make_health(
            sources_health={"canyon": {"status": "degraded", "consecutive_failures": 2}},
        )
        _write_health(use_tmp_health_file, data)
        health.print_health_status()
        captured = capsys.readouterr().out
        assert "consecutive failures: 2" in captured


# ──────────────── --watchdog CLI ────────────────


class TestCheckWatchdog:
    def test_no_health_file(self):
        ok, msg = health.check_watchdog()
        assert not ok
        assert "never run" in msg

    def test_fresh_run(self, use_tmp_health_file):
        _write_health(use_tmp_health_file, _make_health(minutes_ago=30))
        ok, msg = health.check_watchdog()
        assert ok
        assert msg == "OK"

    def test_stale_run(self, use_tmp_health_file):
        _write_health(use_tmp_health_file, _make_health(minutes_ago=180))
        ok, msg = health.check_watchdog()
        assert not ok
        assert "ago" in msg
        assert "Check cron" in msg

    def test_invalid_timestamp(self, use_tmp_health_file):
        data = _make_health()
        data["last_run"] = "not-a-date"
        _write_health(use_tmp_health_file, data)
        ok, msg = health.check_watchdog()
        assert not ok
        assert "invalid" in msg


# ──────────────── _format_timedelta ────────────────


class TestFormatTimedelta:
    def test_seconds(self):
        assert health._format_timedelta(timedelta(seconds=45)) == "45s"

    def test_minutes(self):
        assert health._format_timedelta(timedelta(minutes=15)) == "15m"

    def test_hours(self):
        assert health._format_timedelta(timedelta(hours=3, minutes=15)) == "3h 15m"

    def test_hours_exact(self):
        assert health._format_timedelta(timedelta(hours=2)) == "2h"

    def test_days(self):
        assert health._format_timedelta(timedelta(days=2, hours=5)) == "2d 5h"
