"""Tests for watchlist with price alerts."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from storage.sqlite import SQLiteStorage


@pytest.fixture
def db(tmp_path):
    """Create a temporary SQLiteStorage instance."""
    db_path = tmp_path / "test.db"
    storage = SQLiteStorage(db_path)
    yield storage
    storage.close()


def _seed_deal(db, deal_id="pepper:123", price=10000):
    """Insert a deal for foreign key reference."""
    deal = type("Deal", (), {
        "id": deal_id, "title": "Test Deal", "price": price,
        "link": "https://example.com", "source": "pepper",
        "description": "", "image_url": "", "published_at": "",
        "regular_price": 0,
    })()
    db.upsert_deal(deal, profile="bikes", score=80, category="test")


class TestWatchlistCRUD:
    """Tests for watchlist CRUD operations."""

    def test_add_to_watchlist(self, db):
        _seed_deal(db)
        result = db.add_to_watchlist("pepper:123", 8000)
        assert result is True

    def test_add_duplicate_watchlist(self, db):
        """Adding same deal_id twice returns False."""
        _seed_deal(db)
        db.add_to_watchlist("pepper:123", 8000)
        result = db.add_to_watchlist("pepper:123", 7000)
        assert result is False

    def test_get_watchlist(self, db):
        _seed_deal(db, "pepper:1", 10000)
        _seed_deal(db, "pepper:2", 20000)
        db.add_to_watchlist("pepper:1", 8000)
        db.add_to_watchlist("pepper:2", 15000)
        items = db.get_watchlist()
        assert len(items) == 2
        assert "target_price" in items[0]
        assert "title" in items[0]

    def test_remove_from_watchlist(self, db):
        _seed_deal(db)
        db.add_to_watchlist("pepper:123", 8000)
        result = db.remove_from_watchlist("pepper:123")
        assert result is True
        assert db.get_watchlist() == []

    def test_remove_nonexistent(self, db):
        result = db.remove_from_watchlist("pepper:999")
        assert result is False

    def test_check_watchlist_trigger_price_met(self, db):
        """Price at or below target triggers alert."""
        _seed_deal(db)
        db.add_to_watchlist("pepper:123", 8000)
        trigger = db.check_watchlist_triggers("pepper:123", 7500)
        assert trigger is not None
        assert trigger["target_price"] == 8000

    def test_check_watchlist_trigger_price_not_met(self, db):
        """Price above target does not trigger."""
        _seed_deal(db)
        db.add_to_watchlist("pepper:123", 8000)
        trigger = db.check_watchlist_triggers("pepper:123", 9000)
        assert trigger is None

    def test_check_watchlist_trigger_already_triggered(self, db):
        """Already triggered watchlist entry does not trigger again."""
        _seed_deal(db)
        db.add_to_watchlist("pepper:123", 8000)
        db.check_watchlist_triggers("pepper:123", 7500)
        db.mark_watchlist_triggered("pepper:123")
        trigger = db.check_watchlist_triggers("pepper:123", 7000)
        assert trigger is None

    def test_mark_watchlist_triggered(self, db):
        _seed_deal(db)
        db.add_to_watchlist("pepper:123", 8000)
        db.mark_watchlist_triggered("pepper:123")
        items = db.get_watchlist()
        assert items[0]["triggered_at"] is not None

    def test_get_watchlist_includes_current_price(self, db):
        """Watchlist items include current deal price."""
        _seed_deal(db, "pepper:1", 10000)
        db.add_to_watchlist("pepper:1", 8000)
        items = db.get_watchlist()
        assert items[0]["current_price"] == 10000

    def test_watchlist_not_in_watchlist_deal(self, db):
        """Deal not in watchlist returns None for trigger check."""
        trigger = db.check_watchlist_triggers("pepper:999", 5000)
        assert trigger is None


from unittest.mock import MagicMock, patch


class TestWatchlistTelegram:
    """Tests for watchlist Telegram alert."""

    def test_send_watchlist_alert_format(self):
        """send_watchlist_alert sends properly formatted Polish message."""
        from notifiers.telegram import TelegramNotifier

        notifier = TelegramNotifier("fake-token", "fake-chat")
        deal = type("Deal", (), {
            "id": "pepper:123",
            "title": "Canyon Endurace CF 7",
            "price": 8499,
            "link": "https://pepper.pl/123",
            "source": "pepper",
            "regular_price": 0,
            "alt_links": [],
        })()
        with patch.object(notifier, "_send_message") as mock_send:
            notifier.send_watchlist_alert(deal, target_price=9000, current_price=8499)
            msg = mock_send.call_args[0][0]
            assert "CEL CENOWY" in msg
            assert "Canyon" in msg

    def test_send_watchlist_alert_no_alt_links(self):
        """send_watchlist_alert works without alt_links attribute."""
        from notifiers.telegram import TelegramNotifier

        notifier = TelegramNotifier("fake-token", "fake-chat")
        deal = type("Deal", (), {
            "id": "pepper:123",
            "title": "Test Deal",
            "price": 7000,
            "link": "https://example.com",
            "source": "pepper",
            "regular_price": 0,
            "alt_links": [],
        })()
        with patch.object(notifier, "_send_message") as mock_send:
            notifier.send_watchlist_alert(deal, target_price=8000, current_price=7000)
            mock_send.assert_called_once()
