"""Tests for watchlist with price alerts."""

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from deal_hunter.storage.models import Base
from deal_hunter.storage.repositories import OfferRepository as DealRepository
from deal_hunter.storage.repositories import WatchlistRepository


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
def deal_repo(session):
    return DealRepository(session)


@pytest.fixture
def watchlist_repo(session):
    return WatchlistRepository(session)


def _seed_deal(session, deal_id="pepper:123", price=10000):
    """Insert a deal for foreign key reference."""
    deal_repo = DealRepository(session)
    deal_repo.upsert(
        id=deal_id,
        title="Test Deal",
        price=price,
        link="https://example.com",
        source="pepper",
        description="",
        image_url="",
        profile="bikes",
        score=80,
        category="test",
    )
    session.flush()


class TestWatchlistCRUD:
    """Tests for watchlist CRUD operations."""

    def test_add_to_watchlist(self, session, watchlist_repo):
        _seed_deal(session)
        result = watchlist_repo.add("pepper:123", 8000)
        assert result is True

    def test_add_duplicate_watchlist(self, session, watchlist_repo):
        """Adding same deal_id twice returns False."""
        _seed_deal(session)
        watchlist_repo.add("pepper:123", 8000)
        session.flush()
        result = watchlist_repo.add("pepper:123", 7000)
        assert result is False

    def test_get_watchlist(self, session, watchlist_repo):
        _seed_deal(session, "pepper:1", 10000)
        _seed_deal(session, "pepper:2", 20000)
        watchlist_repo.add("pepper:1", 8000)
        watchlist_repo.add("pepper:2", 15000)
        session.flush()
        items = watchlist_repo.get_all()
        assert len(items) == 2
        assert "target_price" in items[0]
        assert "title" in items[0]

    def test_remove_from_watchlist(self, session, watchlist_repo):
        _seed_deal(session)
        watchlist_repo.add("pepper:123", 8000)
        session.flush()
        result = watchlist_repo.remove("pepper:123")
        assert result is True
        session.flush()
        assert watchlist_repo.get_all() == []

    def test_remove_nonexistent(self, watchlist_repo):
        result = watchlist_repo.remove("pepper:999")
        assert result is False

    def test_check_watchlist_trigger_price_met(self, session, watchlist_repo):
        """Price at or below target triggers alert."""
        _seed_deal(session)
        watchlist_repo.add("pepper:123", 8000)
        session.flush()
        trigger = watchlist_repo.check_trigger("pepper:123", 7500)
        assert trigger is not None
        assert trigger["target_price"] == 8000

    def test_check_watchlist_trigger_price_not_met(self, session, watchlist_repo):
        """Price above target does not trigger."""
        _seed_deal(session)
        watchlist_repo.add("pepper:123", 8000)
        session.flush()
        trigger = watchlist_repo.check_trigger("pepper:123", 9000)
        assert trigger is None

    def test_check_watchlist_trigger_already_triggered(self, session, watchlist_repo):
        """Already triggered watchlist entry does not trigger again."""
        _seed_deal(session)
        watchlist_repo.add("pepper:123", 8000)
        session.flush()
        watchlist_repo.check_trigger("pepper:123", 7500)
        watchlist_repo.mark_triggered("pepper:123")
        session.flush()
        trigger = watchlist_repo.check_trigger("pepper:123", 7000)
        assert trigger is None

    def test_mark_watchlist_triggered(self, session, watchlist_repo):
        _seed_deal(session)
        watchlist_repo.add("pepper:123", 8000)
        session.flush()
        watchlist_repo.mark_triggered("pepper:123")
        session.flush()
        items = watchlist_repo.get_all()
        assert items[0]["triggered_at"] is not None

    def test_get_watchlist_includes_current_price(self, session, watchlist_repo):
        """Watchlist items include current deal price."""
        _seed_deal(session, "pepper:1", 10000)
        watchlist_repo.add("pepper:1", 8000)
        session.flush()
        items = watchlist_repo.get_all()
        assert items[0]["current_price"] == 10000

    def test_watchlist_not_in_watchlist_deal(self, watchlist_repo):
        """Deal not in watchlist returns None for trigger check."""
        trigger = watchlist_repo.check_trigger("pepper:999", 5000)
        assert trigger is None


class TestWatchlistTelegram:
    """Tests for watchlist Telegram alert."""

    def test_send_watchlist_alert_format(self):
        """send_watchlist_alert sends properly formatted Polish message."""
        from deal_hunter.notifiers.telegram import TelegramNotifier

        notifier = TelegramNotifier("fake-token", "fake-chat")
        deal = type(
            "Deal",
            (),
            {
                "id": "pepper:123",
                "title": "Canyon Endurace CF 7",
                "price": 8499,
                "link": "https://pepper.pl/123",
                "source": "pepper",
                "regular_price": 0,
                "alt_links": [],
            },
        )()
        with patch.object(notifier, "_send_message") as mock_send:
            notifier.send_watchlist_alert(deal, target_price=9000, current_price=8499)
            msg = mock_send.call_args[0][0]
            assert "CEL CENOWY" in msg
            assert "Canyon" in msg

    def test_send_watchlist_alert_no_alt_links(self):
        """send_watchlist_alert works without alt_links attribute."""
        from deal_hunter.notifiers.telegram import TelegramNotifier

        notifier = TelegramNotifier("fake-token", "fake-chat")
        deal = type(
            "Deal",
            (),
            {
                "id": "pepper:123",
                "title": "Test Deal",
                "price": 7000,
                "link": "https://example.com",
                "source": "pepper",
                "regular_price": 0,
                "alt_links": [],
            },
        )()
        with patch.object(notifier, "_send_message") as mock_send:
            notifier.send_watchlist_alert(deal, target_price=8000, current_price=7000)
            mock_send.assert_called_once()
