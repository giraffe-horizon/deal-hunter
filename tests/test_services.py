"""Tests for service layer."""

from unittest.mock import MagicMock

import pytest

from filters.base import BaseFilter
from services.types import PriceChange, PriceTrackingConfig
from sources.base import Deal


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


def _make_deal(**overrides):
    defaults = dict(
        id="test:1",
        title="Test Deal",
        price=1000,
        link="http://example.com",
        source="test",
        description="desc",
        temperature=0,
        image_url="",
        published_at="",
    )
    defaults.update(overrides)
    return Deal(**defaults)


class TestDealFetcher:
    def test_deduplicate_by_id(self):
        from services.fetcher import DealFetcher

        fetcher = DealFetcher({})
        deals = [
            _make_deal(id="a", title="First Deal"),
            _make_deal(id="a", title="First Deal"),
            _make_deal(id="b", title="Completely Different Item"),
        ]
        result = fetcher.deduplicate(deals)
        assert len(result) == 2

    def test_deduplicate_fuzzy_merge(self):
        from services.fetcher import DealFetcher

        fetcher = DealFetcher({})
        deals = [
            _make_deal(id="a:1", title="Giant Defy Advanced 2 2024", price=5000, source="pepper"),
            _make_deal(id="b:1", title="Giant Defy Advanced 2 2024", price=5100, source="ceneo"),
        ]
        result = fetcher.deduplicate(deals)
        assert len(result) == 1
        assert len(result[0].alt_links) == 1

    def test_normalize_title(self):
        from services.fetcher import DealFetcher

        assert DealFetcher._normalize_title("  Hello, World!  ") == "hello world"


class TestScoringService:
    def test_get_filter_default(self):
        from services.scorer import ScoringService

        svc = ScoringService({})
        profile = {"score_rules": {"test": 10}, "budget": {"min": 0, "max": 10000}}
        f = svc.get_filter(profile)
        assert isinstance(f, BaseFilter)

    def test_detect_category_match(self):
        from services.scorer import ScoringService

        deal = _make_deal(title="Giant Defy Advanced", description="road bike")
        profile = {"categories": {"bikes": ["bike", "rower"], "parts": ["pedal"]}}
        assert ScoringService.detect_category(deal, profile, "default") == "bikes"

    def test_detect_category_no_match(self):
        from services.scorer import ScoringService

        deal = _make_deal(title="Something else", description="no match")
        profile = {"categories": {"bikes": ["bike"]}}
        assert ScoringService.detect_category(deal, profile, "fallback") == "fallback"

    def test_detect_category_no_categories(self):
        from services.scorer import ScoringService

        deal = _make_deal(title="Anything")
        assert ScoringService.detect_category(deal, {}, "myprofile") == "myprofile"


class TestPriceTracker:
    def test_get_config_defaults(self):
        from services.price_tracker import PriceTracker

        config = PriceTracker.get_config({})
        assert config.enabled is True
        assert config.min_drop_percent == 10

    def test_get_config_custom(self):
        from services.price_tracker import PriceTracker

        config = PriceTracker.get_config(
            {"price_tracking": {"min_drop_percent": 20, "track_increases": True}}
        )
        assert config.min_drop_percent == 20
        assert config.track_increases is True

    def test_no_change_returns_none(self):
        from services.price_tracker import PriceTracker

        repo = MagicMock()
        repo.get_previous_price.return_value = 1000
        tracker = PriceTracker(repo)
        deal = _make_deal(price=1000)
        assert tracker.check_price_change(deal) is None

    def test_small_drop_below_threshold(self):
        from services.price_tracker import PriceTracker

        repo = MagicMock()
        repo.get_previous_price.return_value = 1000
        tracker = PriceTracker(repo)
        deal = _make_deal(price=950)  # 5% drop, below 10% threshold and 200 PLN
        assert tracker.check_price_change(deal) is None

    def test_significant_drop_returns_price_change(self):
        from services.price_tracker import PriceTracker

        repo = MagicMock()
        repo.get_previous_price.return_value = 5000
        repo.get_lowest.return_value = 4500
        tracker = PriceTracker(repo)
        deal = _make_deal(price=4000)  # 20% drop, 1000 PLN
        result = tracker.check_price_change(deal)
        assert result is not None
        assert result.type == "drop"
        assert result.diff_pln == 1000
        assert result.is_lowest_ever is True

    def test_increase_not_reported_by_default(self):
        from services.price_tracker import PriceTracker

        repo = MagicMock()
        repo.get_previous_price.return_value = 1000
        tracker = PriceTracker(repo)
        deal = _make_deal(price=2000)
        assert tracker.check_price_change(deal) is None

    def test_zero_price_returns_none(self):
        from services.price_tracker import PriceTracker

        repo = MagicMock()
        tracker = PriceTracker(repo)
        deal = _make_deal(price=0)
        assert tracker.check_price_change(deal) is None


class TestAlertService:
    def test_is_quiet_hours_no_config(self):
        from services.alerter import is_quiet_hours

        assert is_quiet_hours({}) is False

    def test_send_deal_alerts_no_telegram(self):
        from services.alerter import AlertService

        repo = MagicMock()
        svc = AlertService(telegram=None, alert_repo=repo)
        result = svc.send_deal_alerts(
            [{"deal": _make_deal(), "score": 50, "plus": [], "minus": []}],
            {},
            "test",
            None,
            5,
        )
        assert result == 0

    def test_send_source_failure_no_telegram(self):
        from services.alerter import AlertService

        repo = MagicMock()
        svc = AlertService(telegram=None, alert_repo=repo)
        svc.send_source_failure_alert(["pepper"], {"pepper": {"consecutive_failures": 5}}, None)
        # Should not raise

    def test_flush_queued_empty(self):
        from services.alerter import AlertService

        repo = MagicMock()
        repo.get_pending.return_value = []
        telegram = MagicMock()
        svc = AlertService(telegram=telegram, alert_repo=repo)
        result = svc.flush_queued("test", {}, None, 10)
        assert result == 0
