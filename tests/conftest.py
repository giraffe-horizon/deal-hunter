"""Shared test fixtures."""

from pathlib import Path

import pytest

from sources.base import Deal


@pytest.fixture
def sample_deal() -> Deal:
    """A realistic Deal fixture."""
    return Deal(
        id="pepper:12345",
        title="Giant Defy Advanced 2 2024 rower szosowy XL carbon",
        price=8500,
        link="https://www.pepper.pl/promocje/giant-defy-12345",
        source="pepper",
        description="Rower szosowy Giant Defy Advanced 2, carbon, Shimano 105, 40mm tires",
        temperature=120,
        image_url="https://example.com/image.jpg",
        published_at="2026-03-20T10:00:00+00:00",
    )


@pytest.fixture
def sample_profile() -> dict:
    """A minimal valid profile dict."""
    return {
        "name": "test_profile",
        "emoji": "\U0001f50d",
        "sources": {
            "pepper": {"urls": ["https://www.pepper.pl/search?q=test"]},
        },
        "budget": {"min": 5000, "max": 15000},
        "score_rules": {
            "carbon": 30,
            "shimano": 20,
            "105": 10,
        },
        "penalties": {
            "broken": -50,
            "damaged": -30,
        },
        "excluded_words": ["stolen", "parts only"],
        "required_any": [],
        "score_threshold": 40,
        "score_threshold_alert": 80,
        "telegram": {"topic_id": 31, "max_alerts": 5},
        "notion": None,
        "currency": "PLN",
    }


@pytest.fixture
def tmp_state_dir(tmp_path: Path) -> Path:
    """Temporary directory for state files."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    return state_dir
