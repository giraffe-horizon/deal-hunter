"""Tests for configurable price drop alerts and weekly digest."""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from notifiers.telegram import TelegramNotifier
from services.price_tracker import PriceTracker
from sources.base import Deal
from storage.models import Base
from storage.models import Offer as DealModel
from storage.models import PricePoint as PriceHistory
from storage.repositories import OfferRepository as DealRepository
from storage.repositories import PriceRepository

# ──────────────── FIXTURES ────────────────


@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s


@pytest.fixture
def price_repo(session):
    return PriceRepository(session)


@pytest.fixture
def deal_repo(session):
    return DealRepository(session)


def _seed_deal_with_prices(session, deal_id="pepper:12345", prices=None, profile="bikes"):
    """Insert a deal and its price history."""
    now = datetime.now().isoformat()
    deal = DealModel(
        id=deal_id,
        title="Test Deal",
        price=prices[-1] if prices else 0,
        source="pepper",
        description="",
        image_url="",
        profile=profile,
        score=80,
        category="road",
        status="active",
        first_seen=now,
        last_seen=now,
    )
    session.add(deal)
    session.flush()
    if prices:
        for i, p in enumerate(prices):
            ts = f"2026-04-{10 + i:02d}T10:00:00"
            ph = PriceHistory(deal_id=deal_id, price=p, recorded_at=ts)
            session.add(ph)
    session.flush()


@pytest.fixture
def deal():
    return Deal(
        id="pepper:12345",
        title="Canyon Endurace CF 8 Di2",
        price=10499,
        link="https://example.com/deal/12345",
        source="pepper",
        description="Carbon endurance bike with Shimano Di2",
        temperature=145,
        image_url="https://example.com/img.jpg",
        published_at="2026-04-01T10:00:00",
    )


@pytest.fixture
def deal2():
    return Deal(
        id="ceneo:67890",
        title="Trek Domane SL 6",
        price=10999,
        link="https://ceneo.pl/67890",
        source="ceneo",
        description="Trek Domane SL 6 endurance road bike",
        temperature=0,
        image_url="https://example.com/trek.jpg",
        published_at="2026-04-02T12:00:00",
    )


@pytest.fixture
def profile_with_tracking():
    return {
        "name": "bikes",
        "sources": {"pepper": {}},
        "budget": {"min": 5000, "max": 15000},
        "score_threshold": 50,
        "telegram": {"topic_id": 31},
        "price_tracking": {
            "enabled": True,
            "min_drop_percent": 15,
            "min_drop_amount": 200,
            "track_increases": False,
        },
    }


@pytest.fixture
def profile_no_tracking():
    return {
        "name": "bikes",
        "sources": {"pepper": {}},
        "budget": {"min": 5000, "max": 15000},
        "score_threshold": 50,
        "telegram": {"topic_id": 31},
    }


@pytest.fixture
def profile_tracking_disabled():
    return {
        "name": "bikes",
        "sources": {"pepper": {}},
        "budget": {"min": 5000, "max": 15000},
        "score_threshold": 50,
        "telegram": {"topic_id": 31},
        "price_tracking": {"enabled": False},
    }


# ──────────────── PRICE TRACKING CONFIG ────────────────


class TestPriceTrackingConfig:
    def test_defaults_when_not_specified(self):
        profile = {"name": "test"}
        config = PriceTracker.get_config(profile)
        assert config.enabled is True
        assert config.min_drop_percent == 10
        assert config.min_drop_amount == 200
        assert config.track_increases is False

    def test_custom_values(self, profile_with_tracking):
        config = PriceTracker.get_config(profile_with_tracking)
        assert config.enabled is True
        assert config.min_drop_percent == 15
        assert config.min_drop_amount == 200
        assert config.track_increases is False

    def test_disabled(self, profile_tracking_disabled):
        config = PriceTracker.get_config(profile_tracking_disabled)
        assert config.enabled is False

    def test_partial_override(self):
        profile = {
            "name": "test",
            "price_tracking": {"min_drop_percent": 20},
        }
        config = PriceTracker.get_config(profile)
        assert config.min_drop_percent == 20
        # Defaults for unspecified
        assert config.min_drop_amount == 200
        assert config.enabled is True


# ──────────────── PRICE CHANGE DETECTION ────────────────


class TestCheckPriceChanges:
    def test_no_previous_price_returns_none(self, session, price_repo, deal, profile_with_tracking):
        """First time seen — no previous price — returns None."""
        _seed_deal_with_prices(session, deal.id, prices=[deal.price])
        tracker = PriceTracker(price_repo)
        result = tracker.check_price_change(deal, profile_with_tracking)
        assert result is None

    def test_same_price_no_change(self, session, price_repo, deal, profile_with_tracking):
        """Same price as previous — no change detected."""
        _seed_deal_with_prices(session, deal.id, prices=[10499, 10499])
        tracker = PriceTracker(price_repo)
        result = tracker.check_price_change(deal, profile_with_tracking)
        assert result is None

    def test_significant_drop_percent(self, session, price_repo, deal, profile_with_tracking):
        """Drop of 19% should trigger with min_drop_percent=15."""
        _seed_deal_with_prices(session, deal.id, prices=[12999, 10499])
        tracker = PriceTracker(price_repo)
        result = tracker.check_price_change(deal, profile_with_tracking)
        assert result is not None
        assert result.type == "drop"
        assert result.old_price == 12999
        assert result.new_price == 10499
        assert result.diff_pln == 2500
        assert result.diff_percent == 19.2

    def test_significant_drop_amount(self, session, price_repo, deal, profile_with_tracking):
        """Drop of 300 PLN (2.8%) should trigger with min_drop_amount=200."""
        _seed_deal_with_prices(session, deal.id, prices=[10799, 10499])
        tracker = PriceTracker(price_repo)
        result = tracker.check_price_change(deal, profile_with_tracking)
        assert result is not None
        assert result.type == "drop"
        assert result.diff_pln == 300

    def test_small_drop_below_thresholds(self, session, price_repo, profile_with_tracking):
        """Drop of 100 PLN (1%) should NOT trigger.

        min_drop_amount=200 and min_drop_percent=15.
        """
        small_deal = Deal(
            id="test:1",
            title="Some Bike",
            price=9900,
            link="http://x",
            source="pepper",
            description="",
            temperature=0,
            image_url="",
            published_at="",
        )
        _seed_deal_with_prices(session, "test:1", prices=[10000, 9900])
        tracker = PriceTracker(price_repo)
        result = tracker.check_price_change(small_deal, profile_with_tracking)
        assert result is None

    def test_price_increase_ignored_by_default(self, session, price_repo, profile_with_tracking):
        """Price increase should return None when track_increases=False."""
        increase_deal = Deal(
            id="test:1",
            title="Some Bike",
            price=12000,
            link="http://x",
            source="pepper",
            description="",
            temperature=0,
            image_url="",
            published_at="",
        )
        _seed_deal_with_prices(session, "test:1", prices=[10000, 12000])
        tracker = PriceTracker(price_repo)
        result = tracker.check_price_change(increase_deal, profile_with_tracking)
        assert result is None

    def test_price_increase_tracked_when_enabled(self, session, price_repo):
        profile = {
            "name": "test",
            "price_tracking": {"track_increases": True},
        }
        increase_deal = Deal(
            id="test:1",
            title="Some Bike",
            price=12000,
            link="http://x",
            source="pepper",
            description="",
            temperature=0,
            image_url="",
            published_at="",
        )
        _seed_deal_with_prices(session, "test:1", prices=[10000, 12000])
        tracker = PriceTracker(price_repo)
        result = tracker.check_price_change(increase_deal, profile)
        assert result is not None
        assert result.type == "increase"
        assert result.diff_pln == 2000

    def test_disabled_tracking_returns_none(
        self, session, price_repo, deal, profile_tracking_disabled
    ):
        _seed_deal_with_prices(session, deal.id, prices=[15000, 10499])
        tracker = PriceTracker(price_repo)
        result = tracker.check_price_change(deal, profile_tracking_disabled)
        assert result is None

    def test_zero_price_ignored(self, session, price_repo, profile_with_tracking):
        zero_deal = Deal(
            id="test:1",
            title="Free Bike",
            price=0,
            link="http://x",
            source="pepper",
            description="",
            temperature=0,
            image_url="",
            published_at="",
        )
        tracker = PriceTracker(price_repo)
        result = tracker.check_price_change(zero_deal, profile_with_tracking)
        assert result is None

    def test_lowest_ever_detected(self, session, price_repo, deal, profile_with_tracking):
        """When current price is the all-time lowest, is_lowest_ever=True."""
        _seed_deal_with_prices(session, deal.id, prices=[14000, 12999, 10499])
        tracker = PriceTracker(price_repo)
        result = tracker.check_price_change(deal, profile_with_tracking)
        assert result is not None
        assert result.is_lowest_ever is True

    def test_not_lowest_ever(self, session, price_repo):
        """Price drops but was lower before — not lowest ever."""
        profile = {
            "name": "test",
            "price_tracking": {"min_drop_percent": 5, "min_drop_amount": 50},
        }
        drop_deal = Deal(
            id="test:1",
            title="Some Bike",
            price=11000,
            link="http://x",
            source="pepper",
            description="",
            temperature=0,
            image_url="",
            published_at="",
        )
        _seed_deal_with_prices(session, "test:1", prices=[9000, 12000, 11000])
        tracker = PriceTracker(price_repo)
        result = tracker.check_price_change(drop_deal, profile)
        assert result is not None
        assert result.is_lowest_ever is False

    def test_no_profile_uses_defaults(self, session, price_repo, deal):
        """check_price_change works without profile arg (uses defaults)."""
        _seed_deal_with_prices(session, deal.id, prices=[15000, 10499])
        tracker = PriceTracker(price_repo)
        result = tracker.check_price_change(deal)
        assert result is not None
        assert result.type == "drop"


# ──────────────── SQLITE PRICE QUERIES ────────────────


class TestPriceRepoGetLowestPrice:
    def test_lowest_price(self, session, price_repo, deal):
        _seed_deal_with_prices(session, deal.id, prices=[11000, 9000, 10499])
        assert price_repo.get_lowest(deal.id) == 9000

    def test_lowest_price_nonexistent(self, price_repo):
        assert price_repo.get_lowest("nonexistent:000") is None


class TestPriceRepoGetPreviousPrice:
    def test_previous_price(self, session, price_repo, deal):
        _seed_deal_with_prices(session, deal.id, prices=[10499, 9000])
        # Latest is 9000, previous is 10499
        assert price_repo.get_previous_price(deal.id) == 10499

    def test_previous_price_single_entry(self, session, price_repo, deal):
        _seed_deal_with_prices(session, deal.id, prices=[10499])
        # Only one entry — no previous
        assert price_repo.get_previous_price(deal.id) is None

    def test_previous_price_nonexistent(self, price_repo):
        assert price_repo.get_previous_price("nonexistent:000") is None


class TestPriceRepoGetPriceDrops:
    def test_price_drops_found(self, session, price_repo, deal):
        now = datetime.now()
        _seed_deal_with_prices(session, deal.id, prices=[])
        # Add price history: old high price, then current lower price
        session.execute(
            text(
                "INSERT INTO price_points (deal_id, price, recorded_at) VALUES (:id, :price, :ts)"
            ),
            {"id": deal.id, "price": 12999, "ts": (now - timedelta(days=3)).isoformat()},
        )
        session.execute(
            text(
                "INSERT INTO price_points (deal_id, price, recorded_at) VALUES (:id, :price, :ts)"
            ),
            {"id": deal.id, "price": 10499, "ts": (now - timedelta(hours=1)).isoformat()},
        )
        session.flush()

        drops = price_repo.get_drops(days=7)
        assert len(drops) == 1
        assert drops[0]["old_price"] == 12999
        assert drops[0]["new_price"] == 10499
        assert drops[0]["diff_pln"] == 2500
        assert drops[0]["is_lowest_ever"] is True

    def test_price_drops_with_profile_filter(self, session, price_repo, deal, deal2):
        now = datetime.now()
        _seed_deal_with_prices(session, deal.id, prices=[], profile="bikes")
        _seed_deal_with_prices(session, deal2.id, prices=[], profile="nas_hdd")

        # Price drop for both
        for d in [deal, deal2]:
            session.execute(
                text(
                    "INSERT INTO price_points (deal_id, price, recorded_at)"
                    " VALUES (:id, :price, :ts)"
                ),
                {"id": d.id, "price": d.price + 2000, "ts": (now - timedelta(days=2)).isoformat()},
            )
            session.execute(
                text(
                    "INSERT INTO price_points (deal_id, price, recorded_at)"
                    " VALUES (:id, :price, :ts)"
                ),
                {"id": d.id, "price": d.price, "ts": (now - timedelta(hours=1)).isoformat()},
            )
        session.flush()

        drops = price_repo.get_drops(profile="bikes", days=7)
        assert len(drops) == 1
        assert drops[0]["id"] == deal.id

    def test_price_drops_min_percent_filter(self, session, price_repo, deal):
        now = datetime.now()
        _seed_deal_with_prices(session, deal.id, prices=[])
        # Small drop: 10600 -> 10499 (~1%)
        session.execute(
            text(
                "INSERT INTO price_points (deal_id, price, recorded_at) VALUES (:id, :price, :ts)"
            ),
            {"id": deal.id, "price": 10600, "ts": (now - timedelta(days=2)).isoformat()},
        )
        session.execute(
            text(
                "INSERT INTO price_points (deal_id, price, recorded_at) VALUES (:id, :price, :ts)"
            ),
            {"id": deal.id, "price": 10499, "ts": (now - timedelta(hours=1)).isoformat()},
        )
        session.flush()

        # Should not appear with 5% threshold
        drops = price_repo.get_drops(days=7, min_drop_percent=5)
        assert len(drops) == 0

    def test_no_drops_returns_empty(self, session, price_repo, deal):
        _seed_deal_with_prices(session, deal.id, prices=[10499])
        drops = price_repo.get_drops(days=7)
        assert drops == []

    def test_drops_outside_window_excluded(self, session, price_repo, deal):
        now = datetime.now()
        _seed_deal_with_prices(session, deal.id, prices=[])
        # Old drop (10+ days ago)
        session.execute(
            text(
                "INSERT INTO price_points (deal_id, price, recorded_at) VALUES (:id, :price, :ts)"
            ),
            {"id": deal.id, "price": 15000, "ts": (now - timedelta(days=15)).isoformat()},
        )
        session.execute(
            text(
                "INSERT INTO price_points (deal_id, price, recorded_at) VALUES (:id, :price, :ts)"
            ),
            {"id": deal.id, "price": 10499, "ts": (now - timedelta(days=10)).isoformat()},
        )
        session.flush()

        drops = price_repo.get_drops(days=7)
        assert len(drops) == 0


# ──────────────── TELEGRAM FORMATTING ────────────────


class TestTelegramPriceDropAlert:
    def test_price_drop_message_format(self):
        tg = TelegramNotifier("token", "chat_id")
        deal = Deal(
            id="pepper:12345",
            title="Canyon Endurace CF 8 Di2",
            price=10499,
            link="https://example.com/deal/12345",
            source="pepper",
            description="",
            temperature=0,
            image_url="",
            published_at="",
        )
        price_change = {
            "type": "drop",
            "old_price": 12999,
            "new_price": 10499,
            "diff_pln": 2500,
            "diff_percent": 19.2,
            "is_lowest_ever": True,
        }

        with patch.object(tg, "_send_message") as mock_send:
            tg.send_price_drop_alert(deal, price_change, emoji="\U0001f6b2")
            assert mock_send.called
            msg = mock_send.call_args[0][0]
            assert "SPADEK CENY!" in msg
            assert "Canyon Endurace CF 8 Di2" in msg
            assert "12 999" in msg
            assert "10 499" in msg
            assert "-19%" in msg
            assert "-2 500" in msg
            assert "Najni\u017csza cena w historii!" in msg

    def test_price_drop_message_no_lowest(self):
        tg = TelegramNotifier("token", "chat_id")
        deal = Deal(
            id="test:1",
            title="Some Bike",
            price=11000,
            link="http://x",
            source="pepper",
            description="",
            temperature=0,
            image_url="",
            published_at="",
        )
        price_change = {
            "type": "drop",
            "old_price": 12000,
            "new_price": 11000,
            "diff_pln": 1000,
            "diff_percent": 8.3,
            "is_lowest_ever": False,
        }

        with patch.object(tg, "_send_message") as mock_send:
            tg.send_price_drop_alert(deal, price_change)
            msg = mock_send.call_args[0][0]
            assert "Najni\u017csza cena w historii!" not in msg


class TestTelegramDigest:
    def test_digest_format(self):
        tg = TelegramNotifier("token", "chat_id")
        drops = [
            {
                "title": "Canyon Endurace CF 8",
                "old_price": 12999,
                "new_price": 10499,
                "diff_percent": 19.2,
                "is_lowest_ever": True,
            },
            {
                "title": "Trek Domane SL 6",
                "old_price": 11499,
                "new_price": 10999,
                "diff_percent": 4.3,
                "is_lowest_ever": False,
            },
        ]

        with patch.object(tg, "_send_message") as mock_send:
            tg.send_digest(drops)
            assert mock_send.called
            msg = mock_send.call_args[0][0]
            assert "Tygodniowy przegl\u0105d cen (2 spadk\u00f3w)" in msg
            assert "Canyon Endurace CF 8" in msg
            assert "Trek Domane SL 6" in msg
            assert "\U0001f525" in msg  # lowest ever marker for first drop

    def test_empty_digest_not_sent(self):
        tg = TelegramNotifier("token", "chat_id")
        with patch.object(tg, "_send_message") as mock_send:
            tg.send_digest([])
            assert not mock_send.called


# ──────────────── PROFILE VALIDATION ────────────────


class TestPriceTrackingValidation:
    def test_valid_price_tracking(self):
        from utils.validation import validate_profile

        profile = {
            "name": "test",
            "sources": {"pepper": {}},
            "budget": {"min": 100, "max": 1000},
            "score_threshold": 50,
            "telegram": {"topic_id": 1},
            "price_tracking": {
                "enabled": True,
                "min_drop_percent": 15,
                "min_drop_amount": 200,
                "track_increases": False,
            },
        }
        errors = validate_profile(profile)
        assert len(errors) == 0

    def test_invalid_price_tracking_not_dict(self):
        from utils.validation import validate_profile

        profile = {
            "name": "test",
            "sources": {"pepper": {}},
            "budget": {"min": 100, "max": 1000},
            "score_threshold": 50,
            "telegram": {"topic_id": 1},
            "price_tracking": "invalid",
        }
        errors = validate_profile(profile)
        assert any("price_tracking" in e and "dict" in e for e in errors)

    def test_invalid_min_drop_percent_range(self):
        from utils.validation import validate_profile

        profile = {
            "name": "test",
            "sources": {"pepper": {}},
            "budget": {"min": 100, "max": 1000},
            "score_threshold": 50,
            "telegram": {"topic_id": 1},
            "price_tracking": {"min_drop_percent": 150},
        }
        errors = validate_profile(profile)
        assert any("min_drop_percent" in e and "between" in e for e in errors)

    def test_invalid_min_drop_amount_negative(self):
        from utils.validation import validate_profile

        profile = {
            "name": "test",
            "sources": {"pepper": {}},
            "budget": {"min": 100, "max": 1000},
            "score_threshold": 50,
            "telegram": {"topic_id": 1},
            "price_tracking": {"min_drop_amount": -50},
        }
        errors = validate_profile(profile)
        assert any("min_drop_amount" in e and "non-negative" in e for e in errors)

    def test_invalid_enabled_not_bool(self):
        from utils.validation import validate_profile

        profile = {
            "name": "test",
            "sources": {"pepper": {}},
            "budget": {"min": 100, "max": 1000},
            "score_threshold": 50,
            "telegram": {"topic_id": 1},
            "price_tracking": {"enabled": "yes"},
        }
        errors = validate_profile(profile)
        assert any("enabled" in e and "boolean" in e for e in errors)

    def test_invalid_track_increases_not_bool(self):
        from utils.validation import validate_profile

        profile = {
            "name": "test",
            "sources": {"pepper": {}},
            "budget": {"min": 100, "max": 1000},
            "score_threshold": 50,
            "telegram": {"topic_id": 1},
            "price_tracking": {"track_increases": 1},
        }
        errors = validate_profile(profile)
        assert any("track_increases" in e and "boolean" in e for e in errors)

    def test_no_price_tracking_is_valid(self):
        from utils.validation import validate_profile

        profile = {
            "name": "test",
            "sources": {"pepper": {}},
            "budget": {"min": 100, "max": 1000},
            "score_threshold": 50,
            "telegram": {"topic_id": 1},
        }
        errors = validate_profile(profile)
        assert len(errors) == 0
