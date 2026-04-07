"""E2E test fixtures: live server, seeded database, test profiles."""

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from sources.base import Deal
from storage.sqlite import SQLiteStorage

PROJECT_ROOT = Path(__file__).parent.parent.parent


@pytest.fixture(scope="session")
def e2e_state_dir(tmp_path_factory):
    """Session-scoped temp directory for state files."""
    return tmp_path_factory.mktemp("e2e_state")


@pytest.fixture(scope="session")
def e2e_profiles_dir(tmp_path_factory):
    """Session-scoped temp directory for test profile YAMLs."""
    return tmp_path_factory.mktemp("e2e_profiles")


@pytest.fixture(scope="session")
def seeded_db(e2e_state_dir):
    """Create and seed a SQLite database for E2E tests."""
    db_path = e2e_state_dir / "deals.db"
    db = SQLiteStorage(db_path)
    today = datetime.now().isoformat()

    deal1 = Deal(
        id="pepper:99999",
        title="Test Carbon Bike XL",
        price=8500,
        link="https://example.com/deal/99999",
        source="pepper",
        description="A great carbon bike with Shimano 105",
        temperature=120,
        image_url="https://example.com/img.jpg",
        published_at="2026-04-01T10:00:00",
    )
    db.upsert_deal(deal1, "bikes", 85, category="road")

    deal2 = Deal(
        id="ceneo:88888",
        title="NAS HDD Seagate IronWolf 8TB",
        price=1200,
        link="https://ceneo.pl/88888",
        source="ceneo",
        description="Seagate IronWolf 8TB NAS drive",
        temperature=0,
        image_url="https://example.com/hdd.jpg",
        published_at="2026-04-02T12:00:00",
    )
    db.upsert_deal(deal2, "nas_hdd", 55, category="storage")
    db.update_deal_status("ceneo:88888", "watching")

    deal3 = Deal(
        id="pepper:77777",
        title="Cheap Broken Bike Parts",
        price=200,
        link="https://example.com/deal/77777",
        source="pepper",
        description="Spare parts only",
        temperature=0,
        image_url="",
        published_at="2026-03-15T08:00:00",
    )
    db.upsert_deal(deal3, "bikes", 20, category="")
    db.update_deal_status("pepper:77777", "rejected")

    deal4 = Deal(
        id="pepper:66666",
        title="Brand New Road Bike Today",
        price=5000,
        link="https://example.com/deal/66666",
        source="pepper",
        description="Fresh deal today",
        temperature=50,
        image_url="",
        published_at=today,
    )
    db.upsert_deal(deal4, "bikes", 72, category="road")

    # Price history for deal1 — insert directly with different timestamps to avoid PK dedup
    db._conn.execute(
        "INSERT INTO price_history (deal_id, price, recorded_at) VALUES (?, ?, ?)",
        ("pepper:99999", 9500, "2026-03-20T10:00:00"),
    )
    db._conn.execute(
        "INSERT INTO price_history (deal_id, price, recorded_at) VALUES (?, ?, ?)",
        ("pepper:99999", 8500, "2026-03-25T10:00:00"),
    )
    db._conn.commit()

    db.close()
    return db_path


@pytest.fixture(scope="session")
def test_profiles(e2e_profiles_dir):
    """Write test profile YAMLs to temp dir."""
    bikes = {
        "name": "bikes",
        "emoji": "\U0001f6b2",
        "sources": {"pepper": {"urls": ["https://pepper.pl/search?q=rower"]}},
        "budget": {"min": 1000, "max": 20000},
        "score_rules": {"carbon": 30, "shimano": 20, "105": 10},
        "penalties": {"broken": -50, "damaged": -30},
        "excluded_words": ["stolen", "parts only"],
        "required_any": [],
        "score_threshold": 50,
        "score_threshold_alert": 80,
        "telegram": {"topic_id": 31, "max_alerts": 5},
        "currency": "PLN",
    }
    (e2e_profiles_dir / "bikes.yaml").write_text(
        yaml.dump(bikes, allow_unicode=True), encoding="utf-8"
    )
    return e2e_profiles_dir


@pytest.fixture(scope="session")
def health_json(e2e_state_dir):
    """Write a test health.json file."""
    health_data = {
        "last_run": datetime.now().isoformat(timespec="seconds"),
        "status": "partial",
        "duration_seconds": 12.5,
        "version": "0.10.0",
        "profile_results": {
            "bikes": {
                "status": "ok",
                "deals_found": 15,
                "new_alerts": 3,
                "errors": [],
            },
        },
        "sources_health": {
            "pepper": {
                "status": "ok",
                "last_success": datetime.now().isoformat(),
                "consecutive_failures": 0,
            },
        },
    }
    (e2e_state_dir / "health.json").write_text(json.dumps(health_data))
    return e2e_state_dir / "health.json"


@pytest.fixture(scope="session")
def live_server(seeded_db, test_profiles, health_json, e2e_state_dir):
    """Start the FastAPI server as a subprocess, yield the base URL."""
    env = os.environ.copy()
    env["DEAL_HUNTER_DB_PATH"] = str(seeded_db)
    env["DEAL_HUNTER_PROFILES_DIR"] = str(test_profiles)
    env["DEAL_HUNTER_STATE_DIR"] = str(e2e_state_dir)

    port = 18765
    proc = subprocess.Popen(  # noqa: S603
        [
            sys.executable,
            "-m",
            "uvicorn",
            "dashboard:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    import requests as _req

    base_url = f"http://127.0.0.1:{port}"
    for _ in range(30):
        try:
            _req.get(f"{base_url}/deals", timeout=1)
            break
        except _req.ConnectionError:
            time.sleep(0.3)
    else:
        proc.kill()
        stdout, stderr = proc.communicate()
        raise RuntimeError(
            f"Live server did not start.\nstdout: {stdout.decode()}\nstderr: {stderr.decode()}"
        )

    yield base_url

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="session")
def base_url(live_server):
    """Override pytest-playwright's base_url with our live server."""
    return live_server
