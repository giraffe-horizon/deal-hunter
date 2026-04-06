"""Health monitoring for Deal Hunter.

Tracks run results, source health, and provides watchdog/status checking.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

HEALTH_FILE = Path(__file__).parent / "state" / "health.json"
STALE_THRESHOLD = timedelta(hours=2)
CONSECUTIVE_FAILURE_ALERT_THRESHOLD = 3


def load_health() -> dict | None:
    """Load health.json, returning None if missing or corrupt."""
    if not HEALTH_FILE.exists():
        return None
    try:
        with open(HEALTH_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Failed to read health file: {e}")
        return None


def save_health(data: dict) -> None:
    """Write health.json atomically."""
    HEALTH_FILE.parent.mkdir(exist_ok=True)
    tmp = HEALTH_FILE.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        tmp.replace(HEALTH_FILE)
    except OSError as e:
        logger.error(f"Failed to write health file: {e}")


def compute_overall_status(profile_results: dict) -> str:
    """Determine overall status from profile results.

    - "ok" = all profiles ran without errors
    - "partial" = some profiles/sources had errors but others succeeded
    - "error" = everything failed
    """
    if not profile_results:
        return "error"

    statuses = [r.get("status", "error") for r in profile_results.values()]
    if all(s == "ok" for s in statuses):
        return "ok"
    if all(s == "error" for s in statuses):
        return "error"
    return "partial"


def update_sources_health(
    existing_health: dict | None,
    source_results: dict[str, bool],
) -> dict:
    """Update per-source health tracking.

    source_results: {source_name: True/False} for this run.
    Returns updated sources_health dict.
    """
    now = datetime.now().isoformat()
    prev = {}
    if existing_health and "sources_health" in existing_health:
        prev = existing_health["sources_health"]

    sources_health = {}
    for source_name, success in source_results.items():
        old = prev.get(source_name, {})
        if success:
            sources_health[source_name] = {
                "status": "ok",
                "last_success": now,
                "consecutive_failures": 0,
            }
        else:
            consecutive = old.get("consecutive_failures", 0) + 1
            status = "degraded" if consecutive < CONSECUTIVE_FAILURE_ALERT_THRESHOLD else "down"
            sources_health[source_name] = {
                "status": status,
                "last_success": old.get("last_success", ""),
                "consecutive_failures": consecutive,
            }

    # Preserve sources not seen this run
    for name, data in prev.items():
        if name not in sources_health:
            sources_health[name] = data

    return sources_health


def build_health_data(
    profile_results: dict,
    sources_health: dict,
    duration_seconds: float,
    version: str,
) -> dict:
    """Build the complete health.json payload."""
    return {
        "last_run": datetime.now().isoformat(timespec="seconds"),
        "status": compute_overall_status(profile_results),
        "duration_seconds": round(duration_seconds, 1),
        "version": version,
        "profile_results": profile_results,
        "sources_health": sources_health,
    }


def get_failing_sources(sources_health: dict) -> list[str]:
    """Return source names with consecutive_failures >= threshold."""
    return [
        name
        for name, data in sources_health.items()
        if data.get("consecutive_failures", 0) >= CONSECUTIVE_FAILURE_ALERT_THRESHOLD
    ]


# ──────────────── CLI: --health ────────────────


def print_health_status() -> int:
    """Print human-readable health status. Returns exit code."""
    health = load_health()
    if health is None:
        print("❌ No health data found. Has Deal Hunter ever run?")
        return 3

    last_run_str = health.get("last_run", "")
    try:
        last_run = datetime.fromisoformat(last_run_str)
    except (ValueError, TypeError):
        print("❌ Health file has invalid last_run timestamp")
        return 3

    age = datetime.now() - last_run
    if age > STALE_THRESHOLD:
        age_str = _format_timedelta(age)
        print(f"❌ STALE — last run was {age_str} ago ({last_run.strftime('%Y-%m-%d %H:%M')})")
        return 3

    status = health.get("status", "error")
    status_icon = {"ok": "✅", "partial": "⚠️", "error": "❌"}.get(status, "❓")
    age_str = _format_timedelta(age)

    print(f"Last run: {age_str} ago ({last_run.strftime('%Y-%m-%d %H:%M')})")
    print(f"Status: {status_icon} {status.upper()}")
    print(f"Duration: {health.get('duration_seconds', '?')}s")
    print(f"Version: {health.get('version', '?')}")

    # Per-profile summary
    profiles = health.get("profile_results", {})
    if profiles:
        print(f"\nProfiles ({len(profiles)}):")
        for name, result in profiles.items():
            p_status = result.get("status", "?")
            p_icon = {"ok": "✅", "error": "❌"}.get(p_status, "⚠️")
            deals = result.get("deals_found", 0)
            alerts = result.get("new_alerts", 0)
            errors = result.get("errors", [])
            line = f"  {p_icon} {name}: {deals} deals, {alerts} alerts"
            if errors:
                line += f" — errors: {'; '.join(errors)}"
            print(line)

    # Per-source health
    sources = health.get("sources_health", {})
    if sources:
        print(f"\nSources ({len(sources)}):")
        for name, data in sources.items():
            s_status = data.get("status", "?")
            s_icon = {"ok": "✅", "degraded": "⚠️", "down": "❌"}.get(s_status, "❓")
            failures = data.get("consecutive_failures", 0)
            line = f"  {s_icon} {name}: {s_status}"
            if failures > 0:
                line += f" (consecutive failures: {failures})"
            print(line)

    return {"ok": 0, "partial": 1, "error": 2}.get(status, 2)


# ──────────────── CLI: --watchdog ────────────────


def check_watchdog() -> tuple[bool, str]:
    """Check if last run is fresh. Returns (is_ok, message)."""
    health = load_health()
    if health is None:
        return False, "No health data found — Deal Hunter may have never run."

    last_run_str = health.get("last_run", "")
    try:
        last_run = datetime.fromisoformat(last_run_str)
    except (ValueError, TypeError):
        return False, "Health file has invalid timestamp."

    age = datetime.now() - last_run
    if age > STALE_THRESHOLD:
        age_str = _format_timedelta(age)
        return False, f"Last successful run was {age_str} ago! Check cron."

    return True, "OK"


def _format_timedelta(td: timedelta) -> str:
    """Format timedelta as human-readable string."""
    total_seconds = int(td.total_seconds())
    if total_seconds < 60:
        return f"{total_seconds}s"
    minutes = total_seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    remaining_min = minutes % 60
    if hours < 24:
        return f"{hours}h {remaining_min}m" if remaining_min else f"{hours}h"
    days = hours // 24
    remaining_hours = hours % 24
    return f"{days}d {remaining_hours}h" if remaining_hours else f"{days}d"
