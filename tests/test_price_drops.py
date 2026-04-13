"""Tests for configurable price drop alerts and weekly digest."""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from deal_hunter import check_price_changes, get_price_tracking_config
from notifiers.telegram import TelegramNotifier
from sources.base import Deal
from storage.sqlite import SQLiteStorage

# ──────────────── FIXTURES ────────────────


@pytest.fixture
def db(tmp_path):
    """Create a temporary SQLite database."""
    storage = SQLiteStorage(tmp_path / "test.db")
    yield storage
    storage.close()


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
        config = get_price_tracking_config(profile)
        assert config["enabled"] is True
        assert config["min_drop_percent"] == 10
        assert config["min_drop_amount"] == 200
        assert config["track_increases"] is False

    def test_custom_values(self, profile_with_tracking):
        config = get_price_tracking_config(profile_with_tracking)
        assert config["enabled"] is True
        assert config["min_drop_percent"] == 15
        assert config["min_drop_amount"] == 200
        assert config["track_increases"] is False

    def test_disabled(self, profile_tracking_disabled):
        config = get_price_tracking_config(profile_tracking_disabled)
        assert config["enabled"] is False

    def test_partial_override(self):
        profile = {
            "name": "test",
            "price_tracking": {"min_drop_percent": 20},
        }
        config = get_price_tracking_config(profile)
        assert config["min_drop_percent"] == 20
        # Defaults for unspecified
        assert config["min_drop_amount"] == 200
        assert config["enabled"] is True


# ──────────────── PRICE CHANGE DETECTION ────────────────


class TestCheckPriceChanges:
    def test_first_time_no_change(self, deal, profile_with_tracking):
        state = {"seen": {}, "prices": {}}
        result = check_price_changes(deal, state, "bikes", profile_with_tracking)
        assert result is None
        # Price should be recorded in state
        assert len(state["prices"]) == 1

    def test_same_price_no_change(self, deal, profile_with_tracking):
        state = {
            "seen": {},
            "prices": {"pepper:12345": [{"price": 10499, "ts": "2026-04-01T10:00:00"}]},
        }
        result = check_price_changes(deal, state, "bikes", profile_with_tracking)
        assert result is None

    def test_significant_drop_percent(self, deal, profile_with_tracking):
        """Drop of 19% should trigger with min_drop_percent=15."""
        state = {
            "seen": {},
            "prices": {"pepper:12345": [{"price": 12999, "ts": "2026-04-01T10:00:00"}]},
        }
        result = check_price_changes(deal, state, "bikes", profile_with_tracking)
        assert result is not None
        assert result["type"] == "drop"
        assert result["old_price"] == 12999
        assert result["new_price"] == 10499
        assert result["diff_pln"] == 2500
        assert result["diff_percent"] == 19.2

    def test_significant_drop_amount(self, deal, profile_with_tracking):
        """Drop of 300 PLN (2.8%) should trigger with min_drop_amount=200."""
        state = {
            "seen": {},
            "prices": {"pepper:12345": [{"price": 10799, "ts": "2026-04-01T10:00:00"}]},
        }
        result = check_price_changes(deal, state, "bikes", profile_with_tracking)
        assert result is not None
        assert result["type"] == "drop"
        assert result["diff_pln"] == 300

    def test_small_drop_below_thresholds(self, profile_with_tracking):
        """Drop of 100 PLN (1%) should NOT trigger.

        min_drop_amount=200 and min_drop_percent=15.
        """
        deal = Deal(
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
        state = {
            "seen": {},
            "prices": {"test:1": [{"price": 10000, "ts": "2026-04-01T10:00:00"}]},
        }
        result = check_price_changes(deal, state, "bikes", profile_with_tracking)
        assert result is None

    def test_price_increase_ignored_by_default(self, profile_with_tracking):
        """Price increase should return None when track_increases=False."""
        deal = Deal(
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
        state = {
            "seen": {},
            "prices": {"test:1": [{"price": 10000, "ts": "2026-04-01T10:00:00"}]},
        }
        result = check_price_changes(deal, state, "bikes", profile_with_tracking)
        assert result is None

    def test_price_increase_tracked_when_enabled(self):
        profile = {
            "name": "test",
            "price_tracking": {"track_increases": True},
        }
        deal = Deal(
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
        state = {
            "seen": {},
            "prices": {"test:1": [{"price": 10000, "ts": "2026-04-01T10:00:00"}]},
        }
        result = check_price_changes(deal, state, "bikes", profile)
        assert result is not None
        assert result["type"] == "increase"
        assert result["diff_pln"] == 2000

    def test_disabled_tracking_returns_none(self, deal, profile_tracking_disabled):
        state = {
            "seen": {},
            "prices": {"pepper:12345": [{"price": 15000, "ts": "2026-04-01T10:00:00"}]},
        }
        result = check_price_changes(deal, state, "bikes", profile_tracking_disabled)
        assert result is None

    def test_zero_price_ignored(self, profile_with_tracking):
        deal = Deal(
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
        state = {"seen": {}, "prices": {}}
        result = check_price_changes(deal, state, "bikes", profile_with_tracking)
        assert result is None

    def test_lowest_ever_via_state_json(self, deal, profile_with_tracking):
        """Without SQLite, lowest-ever should be determined from state JSON."""
        state = {
            "seen": {},
            "prices": {
                "pepper:12345": [
                    {"price": 14000, "ts": "2026-03-01T10:00:00"},
                    {"price": 12999, "ts": "2026-04-01T10:00:00"},
                ]
            },
        }
        result = check_price_changes(deal, state, "bikes", profile_with_tracking, db=None)
        assert result is not None
        assert result["is_lowest_ever"] is True

    def test_not_lowest_ever(self):
        """Price drops but was lower before — not lowest ever."""
        profile = {"name": "test", "price_tracking": {"min_drop_percent": 5, "min_drop_amount": 50}}
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
        state = {
            "seen": {},
            "prices": {
                "test:1": [
                    {"price": 9000, "ts": "2026-03-01T10:00:00"},
                    {"price": 12000, "ts": "2026-04-01T10:00:00"},
                ]
            },
        }
        result = check_price_changes(deal, state, "bikes", profile, db=None)
        assert result is not None
        assert result["is_lowest_ever"] is False

    def test_lowest_ever_via_sqlite(self, deal, profile_with_tracking, db):
        """With SQLite, lowest-ever should use db.get_lowest_price()."""
        # Insert deal and price history into SQLite
        db.upsert_deal(deal, "bikes", 100)
        db._conn.execute(
            "INSERT INTO price_history (deal_id, price, recorded_at) VALUES (?, ?, ?)",
            (deal.id, 14000, "2026-03-01T10:00:00"),
        )
        db._conn.commit()

        state = {
            "seen": {},
            "prices": {
                "pepper:12345": [
                    {"price": 12999, "ts": "2026-04-01T10:00:00"},
                ]
            },
        }
        result = check_price_changes(deal, state, "bikes", profile_with_tracking, db=db)
        assert result is not None
        assert result["is_lowest_ever"] is True

    def test_backwards_compat_no_profile(self, deal):
        """check_price_changes works without profile arg (uses defaults)."""
        state = {
            "seen": {},
            "prices": {"pepper:12345": [{"price": 15000, "ts": "2026-04-01T10:00:00"}]},
        }
        result = check_price_changes(deal, state, "bikes")
        assert result is not None
        assert result["type"] == "drop"

    def test_cross_source_no_false_drop(self, profile_with_tracking):
        """Same product from different sources should NOT trigger false price drop."""
        deal_a = Deal(
            id="sprint:100",
            title="BMC URS TWO",
            price=13900,
            link="http://sprint.pl/100",
            source="sprint",
            description="",
            temperature=0,
            image_url="",
            published_at="",
        )
        deal_b = Deal(
            id="centrumrowerowe:200",
            title="BMC URS TWO",
            price=8999,
            link="http://cr.pl/200",
            source="centrumrowerowe",
            description="",
            temperature=0,
            image_url="",
            published_at="",
        )
        state = {"seen": {}, "prices": {}}

        # First source records its price
        result_a = check_price_changes(deal_a, state, "bikes", profile_with_tracking)
        assert result_a is None  # first time, no change

        # Second source should NOT see a price drop from first source
        result_b = check_price_changes(deal_b, state, "bikes", profile_with_tracking)
        assert result_b is None  # first time for this deal.id too

        # Each deal should have its own price history entry
        assert "sprint:100" in state["prices"]
        assert "centrumrowerowe:200" in state["prices"]

    def test_cooldown_suppresses_rapid_drops(self, profile_with_tracking):
        """Price drop within 24h of a previous change should be suppressed."""
        deal = Deal(
            id="test:1",
            title="Some Bike",
            price=8000,
            link="http://x",
            source="pepper",
            description="",
            temperature=0,
            image_url="",
            published_at="",
        )
        now = datetime.now()
        recent_ts = (now - timedelta(hours=2)).isoformat()
        state = {
            "seen": {},
            "prices": {
                "test:1": [
                    {"price": 12000, "ts": "2026-03-01T10:00:00"},
                    {"price": 10000, "ts": recent_ts},  # change 2h ago
                ]
            },
        }
        result = check_price_changes(deal, state, "bikes", profile_with_tracking)
        # Should be suppressed — previous change was only 2h ago
        assert result is None

    def test_cooldown_allows_after_24h(self, profile_with_tracking):
        """Price drop after 24h cooldown should be allowed."""
        deal = Deal(
            id="test:1",
            title="Some Bike",
            price=8000,
            link="http://x",
            source="pepper",
            description="",
            temperature=0,
            image_url="",
            published_at="",
        )
        old_ts = (datetime.now() - timedelta(hours=25)).isoformat()
        state = {
            "seen": {},
            "prices": {
                "test:1": [
                    {"price": 12000, "ts": "2026-03-01T10:00:00"},
                    {"price": 10000, "ts": old_ts},  # change 25h ago
                ]
            },
        }
        result = check_price_changes(deal, state, "bikes", profile_with_tracking)
        assert result is not None
        assert result["type"] == "drop"


# ──────────────── SQLITE STORAGE ────────────────


class TestSQLiteGetLowestPrice:
    def test_lowest_price(self, db, deal):
        db.upsert_deal(deal, "bikes", 100)
        db._conn.execute(
            "INSERT INTO price_history (deal_id, price, recorded_at) VALUES (?, ?, ?)",
            (deal.id, 9000, "2026-03-15T10:00:00"),
        )
        db._conn.execute(
            "INSERT INTO price_history (deal_id, price, recorded_at) VALUES (?, ?, ?)",
            (deal.id, 11000, "2026-03-20T10:00:00"),
        )
        db._conn.commit()
        assert db.get_lowest_price(deal.id) == 9000

    def test_lowest_price_nonexistent(self, db):
        assert db.get_lowest_price("nonexistent:000") is None


class TestSQLiteGetPreviousPrice:
    def test_previous_price(self, db, deal):
        db.upsert_deal(deal, "bikes", 100)
        # Insert a newer price entry after the initial one
        db._conn.execute(
            "INSERT INTO price_history (deal_id, price, recorded_at) VALUES (?, ?, ?)",
            (deal.id, 9000, "2099-01-01T00:00:00"),
        )
        db._conn.commit()
        # Latest is 9000 (2099), previous is deal.price (10499 from upsert)
        assert db.get_previous_price(deal.id) == deal.price

    def test_previous_price_single_entry(self, db, deal):
        db.upsert_deal(deal, "bikes", 100)
        # Only one entry — no previous
        assert db.get_previous_price(deal.id) is None

    def test_previous_price_nonexistent(self, db):
        assert db.get_previous_price("nonexistent:000") is None


class TestSQLiteGetPriceDrops:
    def test_price_drops_found(self, db, deal):
        db.upsert_deal(deal, "bikes", 100)
        now = datetime.now()
        # Add price history: old high price, then current lower price
        db._conn.execute(
            "INSERT INTO price_history (deal_id, price, recorded_at) VALUES (?, ?, ?)",
            (deal.id, 12999, (now - timedelta(days=3)).isoformat()),
        )
        db._conn.execute(
            "INSERT INTO price_history (deal_id, price, recorded_at) VALUES (?, ?, ?)",
            (deal.id, 10499, (now - timedelta(hours=1)).isoformat()),
        )
        db._conn.commit()

        drops = db.get_price_drops(days=7)
        assert len(drops) == 1
        assert drops[0]["old_price"] == 12999
        assert drops[0]["new_price"] == 10499
        assert drops[0]["diff_pln"] == 2500
        assert drops[0]["is_lowest_ever"] is True

    def test_price_drops_with_profile_filter(self, db, deal, deal2):
        now = datetime.now()
        db.upsert_deal(deal, "bikes", 100)
        db.upsert_deal(deal2, "nas_hdd", 80)

        # Price drop for both
        for d in [deal, deal2]:
            db._conn.execute(
                "INSERT INTO price_history (deal_id, price, recorded_at) VALUES (?, ?, ?)",
                (d.id, d.price + 2000, (now - timedelta(days=2)).isoformat()),
            )
            db._conn.execute(
                "INSERT INTO price_history (deal_id, price, recorded_at) VALUES (?, ?, ?)",
                (d.id, d.price, (now - timedelta(hours=1)).isoformat()),
            )
        db._conn.commit()

        drops = db.get_price_drops(profile="bikes", days=7)
        assert len(drops) == 1
        assert drops[0]["id"] == deal.id

    def test_price_drops_min_percent_filter(self, db, deal):
        now = datetime.now()
        db.upsert_deal(deal, "bikes", 100)
        # Small drop: 10499 -> 10400 (~1%)
        db._conn.execute(
            "INSERT INTO price_history (deal_id, price, recorded_at) VALUES (?, ?, ?)",
            (deal.id, 10600, (now - timedelta(days=2)).isoformat()),
        )
        db._conn.execute(
            "INSERT INTO price_history (deal_id, price, recorded_at) VALUES (?, ?, ?)",
            (deal.id, 10499, (now - timedelta(hours=1)).isoformat()),
        )
        db._conn.commit()

        # Should not appear with 5% threshold
        drops = db.get_price_drops(days=7, min_drop_percent=5)
        assert len(drops) == 0

    def test_no_drops_returns_empty(self, db, deal):
        db.upsert_deal(deal, "bikes", 100)
        drops = db.get_price_drops(days=7)
        assert drops == []

    def test_drops_outside_window_excluded(self, db, deal):
        now = datetime.now()
        db.upsert_deal(deal, "bikes", 100)
        # Old drop (10 days ago)
        db._conn.execute(
            "INSERT INTO price_history (deal_id, price, recorded_at) VALUES (?, ?, ?)",
            (deal.id, 15000, (now - timedelta(days=15)).isoformat()),
        )
        db._conn.execute(
            "INSERT INTO price_history (deal_id, price, recorded_at) VALUES (?, ?, ?)",
            (deal.id, 10499, (now - timedelta(days=10)).isoformat()),
        )
        db._conn.commit()

        drops = db.get_price_drops(days=7)
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
