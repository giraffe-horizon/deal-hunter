"""Tests for the interactive profile creator (--init)."""

from collections import OrderedDict
from unittest.mock import MagicMock

import yaml

from deal_hunter.utils.init_profile import run_init

# Fixed registry so tests don't break when new stores are added.
# First entry is a search-type YAML store (accepts queries).
_FIXED_REGISTRY = OrderedDict(
    [
        ("fake_store", MagicMock()),
        ("pepper", MagicMock()),
        ("web", MagicMock()),
    ]
)

_FIXED_STORE_DEFS = {
    "fake_store": {"name": "fake_store", "type": "search"},
}


def test_init_creates_valid_profile(tmp_path, monkeypatch):
    """Test that run_init() creates a valid YAML profile from user input."""
    # Simulate user input sequence:
    # 1. Profile name: "test_gadgets"
    # 2. Emoji: (accept default)
    # 3. Source selection: "1" (first available — fake_store, search type)
    # 4. Source config (queries for search-type): "wireless speaker, bluetooth"
    # 5. Budget min: "50"
    # 6. Budget max: "300"
    # 7. Score keywords: "sony, jbl, bose"
    # 8. Excluded words: "broken, refurbished"
    # 9. Telegram: "y"
    # 10. Topic ID: "0"
    # 11. Max alerts: "5"
    inputs = iter(
        [
            "test_gadgets",  # profile name
            "",  # emoji (default)
            "1",  # source selection (first available — fake_store)
            "wireless speaker, bluetooth",  # queries for fake_store
            "50",  # budget min
            "300",  # budget max
            "sony, jbl, bose",  # score keywords
            "broken, refurbished",  # excluded words
            "y",  # enable telegram
            "0",  # topic id
            "5",  # max alerts
        ]
    )

    def mock_input(prompt=""):
        return next(inputs)

    monkeypatch.setattr("builtins.input", mock_input)
    monkeypatch.setattr("deal_hunter.utils.init_profile.SOURCE_REGISTRY", _FIXED_REGISTRY)
    monkeypatch.setattr(
        "deal_hunter.utils.init_profile.load_all_store_definitions", lambda: _FIXED_STORE_DEFS
    )

    # Redirect profiles dir to tmp
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    monkeypatch.setattr("deal_hunter.utils.init_profile.PROFILES_DIR", profiles_dir)

    run_init()

    # Verify profile was created
    profile_path = profiles_dir / "test_gadgets.yaml"
    assert profile_path.exists(), "Profile file was not created"

    # Parse and verify content
    content = profile_path.read_text(encoding="utf-8")
    assert "name: test_gadgets" in content
    assert "score_rules:" in content
    assert "budget:" in content

    # Verify it's valid YAML (strip comments, load)
    # The file uses custom formatting, but should still be valid YAML
    parsed = yaml.safe_load(content)
    assert parsed["name"] == "test_gadgets"
    assert parsed["budget"]["min"] == 50
    assert parsed["budget"]["max"] == 300
    assert "sony" in parsed["score_rules"]
    assert parsed["score_rules"]["sony"] == 30
    assert "broken" in parsed.get("excluded_words", [])


def test_init_handles_keyboard_interrupt(monkeypatch, capsys):
    """Test that Ctrl+C is handled gracefully."""

    def mock_input(prompt=""):
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", mock_input)

    # Should not raise
    run_init()

    captured = capsys.readouterr()
    assert "Aborted" in captured.out


def test_init_handles_eof(monkeypatch, capsys):
    """Test that EOFError (piped input ending) is handled gracefully."""

    def mock_input(prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", mock_input)

    run_init()

    captured = capsys.readouterr()
    assert "Aborted" in captured.out


def test_init_rejects_invalid_name(tmp_path, monkeypatch, capsys):
    """Test that invalid profile names are rejected and re-prompted."""
    inputs = iter(
        [
            "BAD NAME",  # invalid (uppercase + space)
            "good_name",  # valid name
            "",  # emoji (default)
            "1",  # source selection (fake_store)
            "test query",  # source config
            "100",  # budget min
            "500",  # budget max
            "keyword",  # score keywords
            "",  # no excluded words
            "y",  # telegram
            "0",  # topic id
            "5",  # max alerts
        ]
    )

    def mock_input(prompt=""):
        return next(inputs)

    monkeypatch.setattr("builtins.input", mock_input)
    monkeypatch.setattr("deal_hunter.utils.init_profile.SOURCE_REGISTRY", _FIXED_REGISTRY)
    monkeypatch.setattr(
        "deal_hunter.utils.init_profile.load_all_store_definitions", lambda: _FIXED_STORE_DEFS
    )

    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    monkeypatch.setattr("deal_hunter.utils.init_profile.PROFILES_DIR", profiles_dir)

    run_init()

    captured = capsys.readouterr()
    assert "lowercase" in captured.out
    assert (profiles_dir / "good_name.yaml").exists()


def test_init_no_sources_aborts(tmp_path, monkeypatch, capsys):
    """Test that selecting no sources aborts gracefully."""
    inputs = iter(
        [
            "test_empty",  # profile name
            "",  # emoji
            "",  # no sources selected
        ]
    )

    def mock_input(prompt=""):
        return next(inputs)

    monkeypatch.setattr("builtins.input", mock_input)
    monkeypatch.setattr("deal_hunter.utils.init_profile.SOURCE_REGISTRY", _FIXED_REGISTRY)
    monkeypatch.setattr(
        "deal_hunter.utils.init_profile.load_all_store_definitions", lambda: _FIXED_STORE_DEFS
    )

    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    monkeypatch.setattr("deal_hunter.utils.init_profile.PROFILES_DIR", profiles_dir)

    run_init()

    captured = capsys.readouterr()
    assert "No sources configured" in captured.out
    assert not (profiles_dir / "test_empty.yaml").exists()
