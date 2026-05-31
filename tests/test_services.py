"""Tests for service layer."""

from unittest.mock import MagicMock

import pytest

from deal_hunter.core.types import PriceChange, PriceTrackingConfig
from deal_hunter.domain.scoring.base import BaseFilter
from deal_hunter.sources.base import Deal


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
        from deal_hunter.services.profile_manager import ProfileManager

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
        from deal_hunter.services.fetcher import DealFetcher

        fetcher = DealFetcher({})
        deals = [
            _make_deal(id="a", title="First Deal"),
            _make_deal(id="a", title="First Deal"),
            _make_deal(id="b", title="Completely Different Item"),
        ]
        result = fetcher.deduplicate(deals)
        assert len(result) == 2

    def test_deduplicate_fuzzy_merge(self):
        from deal_hunter.services.fetcher import DealFetcher

        fetcher = DealFetcher({})
        deals = [
            _make_deal(id="a:1", title="Giant Defy Advanced 2 2024", price=5000, source="pepper"),
            _make_deal(id="b:1", title="Giant Defy Advanced 2 2024", price=5100, source="ceneo"),
        ]
        result = fetcher.deduplicate(deals)
        assert len(result) == 1
        assert len(result[0].alt_links) == 1

    def test_normalize_title(self):
        from deal_hunter.services.fetcher import DealFetcher

        assert DealFetcher._normalize_title("  Hello, World!  ") == "hello world"


class TestScoringService:
    def test_get_filter_default(self):
        from deal_hunter.services.scorer import ScoringService

        svc = ScoringService({})
        profile = {"score_rules": {"test": 10}, "budget": {"min": 0, "max": 10000}}
        f = svc.get_filter(profile)
        assert isinstance(f, BaseFilter)

    def test_detect_category_match(self):
        from deal_hunter.services.scorer import ScoringService

        deal = _make_deal(title="Giant Defy Advanced", description="road bike")
        profile = {"categories": {"bikes": ["bike", "rower"], "parts": ["pedal"]}}
        assert ScoringService.detect_category(deal, profile, "default") == "bikes"

    def test_detect_category_no_match(self):
        from deal_hunter.services.scorer import ScoringService

        deal = _make_deal(title="Something else", description="no match")
        profile = {"categories": {"bikes": ["bike"]}}
        assert ScoringService.detect_category(deal, profile, "fallback") == "fallback"

    def test_detect_category_no_categories(self):
        from deal_hunter.services.scorer import ScoringService

        deal = _make_deal(title="Anything")
        assert ScoringService.detect_category(deal, {}, "myprofile") == "myprofile"


class TestPriceTracker:
    def test_get_config_defaults(self):
        from deal_hunter.services.price_tracker import PriceTracker

        config = PriceTracker.get_config({})
        assert config.enabled is True
        assert config.min_drop_percent == 10

    def test_get_config_custom(self):
        from deal_hunter.services.price_tracker import PriceTracker

        config = PriceTracker.get_config(
            {"price_tracking": {"min_drop_percent": 20, "track_increases": True}}
        )
        assert config.min_drop_percent == 20
        assert config.track_increases is True

    def test_no_change_returns_none(self):
        from deal_hunter.services.price_tracker import PriceTracker

        repo = MagicMock()
        repo.get_previous_price.return_value = 1000
        tracker = PriceTracker(repo)
        deal = _make_deal(price=1000)
        assert tracker.check_price_change(deal) is None

    def test_small_drop_below_threshold(self):
        from deal_hunter.services.price_tracker import PriceTracker

        repo = MagicMock()
        repo.get_previous_price.return_value = 1000
        tracker = PriceTracker(repo)
        deal = _make_deal(price=950)  # 5% drop, below 10% threshold and 200 PLN
        assert tracker.check_price_change(deal) is None

    def test_significant_drop_returns_price_change(self):
        from deal_hunter.services.price_tracker import PriceTracker

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
        from deal_hunter.services.price_tracker import PriceTracker

        repo = MagicMock()
        repo.get_previous_price.return_value = 1000
        tracker = PriceTracker(repo)
        deal = _make_deal(price=2000)
        assert tracker.check_price_change(deal) is None

    def test_zero_price_returns_none(self):
        from deal_hunter.services.price_tracker import PriceTracker

        repo = MagicMock()
        tracker = PriceTracker(repo)
        deal = _make_deal(price=0)
        assert tracker.check_price_change(deal) is None


class TestAlertService:
    def test_is_quiet_hours_no_config(self):
        from deal_hunter.services.alerter import is_quiet_hours

        assert is_quiet_hours({}) is False

    def test_send_deal_alerts_no_telegram(self):
        from deal_hunter.services.alerter import AlertService

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
        from deal_hunter.services.alerter import AlertService

        repo = MagicMock()
        svc = AlertService(telegram=None, alert_repo=repo)
        svc.send_source_failure_alert(["pepper"], {"pepper": {"consecutive_failures": 5}}, None)
        # Should not raise

    def test_flush_queued_empty(self):
        from deal_hunter.services.alerter import AlertService

        repo = MagicMock()
        repo.get_pending.return_value = []
        telegram = MagicMock()
        svc = AlertService(telegram=telegram, alert_repo=repo)
        result = svc.flush_queued("test", {}, None, 10)
        assert result == 0


class TestHealthTracker:
    @pytest.fixture
    def health_file(self, tmp_path):
        return tmp_path / "health.json"

    @pytest.fixture
    def tracker(self, health_file):
        from deal_hunter.services.health_tracker import HealthTracker

        return HealthTracker(health_file)

    def test_load_missing(self, tracker):
        assert tracker.load() is None

    def test_save_and_load(self, tracker, health_file):
        data = {"status": "ok", "last_run": "2024-01-01T12:00:00"}
        tracker.save(data)
        assert health_file.exists()
        loaded = tracker.load()
        assert loaded["status"] == "ok"

    def test_compute_status_all_ok(self, tracker):
        results = {"bikes": {"status": "ok"}, "nas": {"status": "ok"}}
        assert tracker._compute_status(results) == "ok"

    def test_compute_status_mixed(self, tracker):
        results = {"bikes": {"status": "ok"}, "nas": {"status": "error"}}
        assert tracker._compute_status(results) == "partial"

    def test_compute_status_all_error(self, tracker):
        results = {"bikes": {"status": "error"}}
        assert tracker._compute_status(results) == "error"

    def test_compute_status_empty(self, tracker):
        assert tracker._compute_status({}) == "error"

    def test_format_timedelta_seconds(self, tracker):
        from datetime import timedelta

        assert tracker._format_timedelta(timedelta(seconds=30)) == "30s"

    def test_format_timedelta_hours(self, tracker):
        from datetime import timedelta

        assert tracker._format_timedelta(timedelta(hours=2, minutes=15)) == "2h 15m"

    def test_get_failing_sources(self, tracker):
        sources = {
            "pepper": {"consecutive_failures": 5},
            "ceneo": {"consecutive_failures": 1},
        }
        failing = tracker.get_failing_sources(sources)
        assert "pepper" in failing
        assert "ceneo" not in failing


def test_alert_service_filters_muted_deal_before_send():
    """A deal with muted_until in the future must not enter alert_queue nor reach Telegram."""
    import pytest as _pytest
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from deal_hunter.core.notification_config import NotificationConfig
    from deal_hunter.services.alerter import AlertService
    from deal_hunter.storage.models import Base
    from deal_hunter.storage.repositories import (
        AlertQueueRepository,
        OfferRepository,
        SentNotificationRepository,
    )

    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    with Session(eng) as session:
        offer_repo = OfferRepository(session)
        alert_repo = AlertQueueRepository(session)
        sent_repo = SentNotificationRepository(session)
        offer_repo.upsert(
            id="pepper:42",
            title="Test",
            price=100,
            link="",
            source="x",
            description="",
            image_url="",
            profile="bikes",
            score=0,
            category="",
            status="active",
            first_seen="2026-05-01T00:00:00",
            last_seen="2026-05-01T00:00:00",
        )
        offer_repo.set_muted_until("pepper:42", "2099-01-01T00:00:00")
        session.commit()

        telegram = type(
            "FakeTG",
            (),
            {
                "send_price_drop_alert": lambda *a, **k: _pytest.fail("must not be called"),
            },
        )()
        svc = AlertService(telegram, alert_repo, offer_repo=offer_repo, sent_repo=sent_repo)

        deal = type("D", (), {"id": "pepper:42", "title": "Test", "link": ""})()
        drops = [
            {
                "deal": deal,
                "price_change": {
                    "type": "drop",
                    "old_price": 200,
                    "new_price": 100,
                    "diff_pln": 100,
                    "diff_percent": 50.0,
                    "is_lowest_ever": False,
                },
            }
        ]
        cfg = NotificationConfig(7, True, 30)
        sent = svc.send_price_drop_alerts(
            drops,
            profile={},
            profile_name="bikes",
            topic_id=None,
            max_alerts=5,
            notification_config=cfg,
        )
        assert sent == 0
        assert alert_repo.get_pending() == []


class TestAlertServiceRecording:
    """Verifies the alerter threads `profile` and records generic sends."""

    def _setup(self, monkeypatch):
        from deal_hunter.notifiers.telegram import transport as tr

        captured: list[dict] = []

        def _capture(**kw):
            captured.append(kw)

        # Patch BOTH the transport import and the alerter import (alerter
        # imports record_sent_notification directly).
        monkeypatch.setattr(tr, "record_sent_notification", _capture)
        from deal_hunter.services import alerter as alerter_mod

        monkeypatch.setattr(alerter_mod, "record_sent_notification", _capture)
        return captured

    def test_send_deal_alerts_passes_profile(self, monkeypatch):
        from deal_hunter.services.alerter import AlertService

        self._setup(monkeypatch)

        recorded_kwargs: list[dict] = []

        class FakeTG:
            def send_alert(self, *a, **k):
                recorded_kwargs.append(k)

            def send_summary(self, *a, **k):
                recorded_kwargs.append(k)

        svc = AlertService(FakeTG())
        deal = type("D", (), {"id": "pepper:1", "title": "x", "price": 100, "link": ""})()
        svc.send_deal_alerts(
            [{"deal": deal, "score": 80, "plus": [], "minus": []}],
            profile={},
            profile_name="bikes",
            topic_id=None,
            max_alerts=5,
        )
        assert recorded_kwargs[0]["profile"] == "bikes"

    def test_flush_queued_records_each_flushed_alert(self, monkeypatch):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session

        from deal_hunter.services.alerter import AlertService
        from deal_hunter.storage.models import Base
        from deal_hunter.storage.repositories import AlertQueueRepository

        captured = self._setup(monkeypatch)
        eng = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(eng)
        with Session(eng) as session:
            alert_repo = AlertQueueRepository(session)
            alert_repo.queue(
                "bikes",
                "price_drop",
                '{"deal_id":"pepper:1","title":"x","old_price":200,"new_price":100}',
                deal_id="pepper:1",
            )
            session.commit()

            class FakeTG:
                def send_text(self, *_a, **_k):
                    return True  # success

            svc = AlertService(FakeTG(), alert_repo)
            sent = svc.flush_queued("bikes", profile={}, topic_id=None, max_alerts=5)
            assert sent == 1
        assert len(captured) == 1
        assert captured[0]["alert_type"] == "price_drop"
        assert captured[0]["deal_id"] == "pepper:1"
        assert captured[0]["profile"] == "bikes"

    def test_flush_queued_does_not_record_or_mark_sent_on_send_failure(self, monkeypatch):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session

        from deal_hunter.services.alerter import AlertService
        from deal_hunter.storage.models import Base
        from deal_hunter.storage.repositories import AlertQueueRepository

        captured = self._setup(monkeypatch)
        eng = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(eng)
        with Session(eng) as session:
            alert_repo = AlertQueueRepository(session)
            alert_repo.queue("bikes", "deal", "{}", deal_id="pepper:1")
            session.commit()

            class FakeTG:
                def send_text(self, *_a, **_k):
                    return False  # failure

            sent = AlertService(FakeTG(), alert_repo).flush_queued("bikes", {}, None, 5)
            # Failed send → not recorded AND not marked-sent (still pending next run).
            assert sent == 0
            assert len(alert_repo.get_pending(profile="bikes")) == 1
        assert captured == []

    def test_send_source_failure_alert_records(self, monkeypatch):
        from deal_hunter.services.alerter import AlertService

        captured = self._setup(monkeypatch)

        class FakeTG:
            def send_text(self, *_a, **_k):
                return True

        svc = AlertService(FakeTG())
        svc.send_source_failure_alert(
            ["pepper"], {"pepper": {"consecutive_failures": 5, "last_success": "n"}}, None
        )
        assert len(captured) == 1
        assert captured[0]["alert_type"] == "source_failure"
        assert captured[0]["profile"] is None
        assert "text_preview" in captured[0]["payload"]


def test_cooldown_reads_from_sent_notifications():
    """A recent row in sent_notifications must trigger cooldown suppression."""
    from datetime import datetime

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from deal_hunter.core.notification_config import NotificationConfig
    from deal_hunter.services.alerter import AlertService
    from deal_hunter.storage.models import Base
    from deal_hunter.storage.repositories import (
        AlertQueueRepository,
        OfferRepository,
        SentNotificationRepository,
    )

    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    with Session(eng) as session:
        offer_repo = OfferRepository(session)
        alert_repo = AlertQueueRepository(session)
        sent_repo = SentNotificationRepository(session)

        offer_repo.upsert(
            id="pepper:99",
            title="x",
            price=100,
            link="",
            source="x",
            description="",
            image_url="",
            profile="bikes",
            score=0,
            category="",
            status="active",
            first_seen="2026-05-01T00:00:00",
            last_seen="2026-05-01T00:00:00",
        )
        sent_repo.record(
            alert_type="price_drop",
            payload_json='{"x": 1}',
            deal_id="pepper:99",
            sent_at=datetime.now().isoformat(),  # now → in cooldown
        )
        session.commit()

        telegram = type(
            "FakeTG",
            (),
            {
                "send_price_drop_alert": lambda *a, **k: (_ for _ in ()).throw(
                    AssertionError("must not be called")
                ),
            },
        )()
        svc = AlertService(telegram, alert_repo, offer_repo=offer_repo, sent_repo=sent_repo)
        deal = type("D", (), {"id": "pepper:99", "title": "x", "link": ""})()
        drops = [
            {
                "deal": deal,
                "price_change": {
                    "type": "drop",
                    "old_price": 200,
                    "new_price": 100,
                    "diff_pln": 100,
                    "diff_percent": 50.0,
                    "is_lowest_ever": False,
                },
            }
        ]
        cfg = NotificationConfig(
            cooldown_days=7, alert_through_cooldown_if_ath_low=True, default_snooze_days=30
        )
        sent = svc.send_price_drop_alerts(
            drops,
            profile={},
            profile_name="bikes",
            topic_id=None,
            max_alerts=5,
            notification_config=cfg,
        )
        assert sent == 0
