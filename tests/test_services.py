"""Tests for service layer."""

import pytest

from services.types import PriceChange, PriceTrackingConfig


def test_price_tracking_config_defaults():
    config = PriceTrackingConfig()
    assert config.enabled is True
    assert config.min_drop_percent == 10
    assert config.min_drop_amount == 200
    assert config.track_increases is False


def test_price_change_dataclass():
    pc = PriceChange(
        deal_id="pepper:1",
        type="drop",
        old_price=5000,
        new_price=4000,
        diff_pln=1000,
        diff_percent=20.0,
        is_lowest_ever=True,
    )
    assert pc.diff_pln == 1000
    assert pc.type == "drop"


class TestProfileManager:
    @pytest.fixture
    def profiles_dir(self, tmp_path):
        d = tmp_path / "profiles"
        d.mkdir()
        (d / "bikes.yaml").write_text("name: bikes\nemoji: '🚲'\nscore_threshold: 50\n")
        (d / "nas.yaml").write_text("name: nas\nemoji: '💾'\nenabled: false\n")
        return d

    @pytest.fixture
    def mgr(self, profiles_dir):
        from services.profile_manager import ProfileManager

        return ProfileManager(profiles_dir)

    def test_list_all(self, mgr):
        names = mgr.list_all()
        assert "bikes" in names
        assert "nas" in names

    def test_list_enabled_only(self, mgr):
        names = mgr.list_all(include_disabled=False)
        assert "bikes" in names
        assert "nas" not in names

    def test_load(self, mgr):
        data = mgr.load("bikes")
        assert data["name"] == "bikes"

    def test_load_missing_returns_none(self, mgr):
        assert mgr.load("nonexistent") is None

    def test_safe_path_valid(self, mgr):
        path = mgr.safe_path("bikes")
        assert path is not None
        assert path.name == "bikes.yaml"

    def test_safe_path_traversal_rejected(self, mgr):
        assert mgr.safe_path("../etc/passwd") is None
        assert mgr.safe_path("") is None
        assert mgr.safe_path("a" * 100) is None
