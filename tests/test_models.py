"""Tests for SQLAlchemy ORM models."""

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from deal_hunter.storage.models import (
    AlertQueue,
    Base,
    Feedback,
    SeenDeal,
    WatchlistItem,
)
from deal_hunter.storage.models import (
    Offer as Deal,
)
from deal_hunter.storage.models import (
    PricePoint as PriceHistory,
)


@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s


class TestTableCreation:
    def test_all_tables_created(self, engine):
        tables = inspect(engine).get_table_names()
        assert set(tables) == {
            "offers",
            "price_points",
            "feedback",
            "alert_queue",
            "watchlist",
            "seen_deals",
            "products",
            "product_aliases",
            "offer_payload_history",
            "deal_events",
            "match_reviews",
            "match_decisions",
            "fx_rates",
        }

    def test_deals_columns(self, engine):
        cols = {c["name"] for c in inspect(engine).get_columns("offers")}
        assert cols == {
            "id",
            "raw_title",
            "current_price_pln",
            "url",
            "source",
            "description",
            "image_url",
            "profile",
            "score",
            "category",
            "status",
            "first_seen_at",
            "last_seen_at",
            "product_id",
            "source_native_id",
            "current_price_original",
            "currency_original",
            "fx_rate_used",
            "availability",
            "attributes_hint",
            "is_active",
        }

    def test_price_points_columns(self, engine):
        cols = {c["name"] for c in inspect(engine).get_columns("price_points")}
        assert cols == {
            "offer_id",
            "price_pln",
            "recorded_at",
            "product_id",
            "price_original",
            "currency_original",
            "fx_rate_used",
            "availability",
        }

    def test_seen_deals_columns(self, engine):
        cols = {c["name"] for c in inspect(engine).get_columns("seen_deals")}
        assert cols == {"id", "deal_id", "profile", "dedup_key", "first_seen_at"}


class TestDealModel:
    def test_create_deal(self, session):
        deal = Deal(
            id="pepper:123",
            raw_title="Test Deal",
            current_price_pln=1000,
            url="https://example.com",
            source="pepper",
            description="desc",
            image_url="",
            profile="bikes",
            score=80,
            category="road",
            status="active",
            first_seen_at="2026-04-13T10:00:00",
            last_seen_at="2026-04-13T10:00:00",
        )
        session.add(deal)
        session.commit()

        loaded = session.get(Deal, "pepper:123")
        assert loaded is not None
        assert loaded.raw_title == "Test Deal"
        assert loaded.current_price_pln == 1000
        assert loaded.status == "active"

    def test_deal_relationships(self, session):
        deal = Deal(
            id="pepper:456",
            raw_title="Bike",
            current_price_pln=5000,
            url="https://example.com",
            source="pepper",
            description="",
            image_url="",
            profile="bikes",
            score=70,
            category="",
            status="active",
            first_seen_at="2026-04-13T10:00:00",
            last_seen_at="2026-04-13T10:00:00",
        )
        session.add(deal)
        session.flush()

        ph = PriceHistory(offer_id="pepper:456", price_pln=5000, recorded_at="2026-04-13T10:00:00")
        session.add(ph)
        session.commit()

        loaded = session.get(Deal, "pepper:456")
        assert len(loaded.prices) == 1
        assert loaded.prices[0].price_pln == 5000

    def test_deal_feedback_entries_relationship(self, session):
        deal = Deal(
            id="pepper:rel-fb",
            raw_title="Feedback Rel Deal",
            current_price_pln=2000,
            url="https://example.com",
            source="pepper",
            description="",
            image_url="",
            profile="bikes",
            score=60,
            category="",
            status="active",
            first_seen_at="2026-04-13T10:00:00",
            last_seen_at="2026-04-13T10:00:00",
        )
        session.add(deal)
        session.flush()

        fb1 = Feedback(deal_id="pepper:rel-fb", action="watch", created_at="2026-04-13T10:00:00")
        fb2 = Feedback(deal_id="pepper:rel-fb", action="skip", created_at="2026-04-13T11:00:00")
        session.add_all([fb1, fb2])
        session.commit()

        loaded = session.get(Deal, "pepper:rel-fb")
        actions = {e.action for e in loaded.feedback_entries}
        assert actions == {"watch", "skip"}

    def test_deal_watchlist_entry_relationship(self, session):
        deal = Deal(
            id="pepper:rel-wl",
            raw_title="Watchlist Rel Deal",
            current_price_pln=3000,
            url="https://example.com",
            source="pepper",
            description="",
            image_url="",
            profile="bikes",
            score=55,
            category="",
            status="active",
            first_seen_at="2026-04-13T10:00:00",
            last_seen_at="2026-04-13T10:00:00",
        )
        session.add(deal)
        session.flush()

        wl = WatchlistItem(
            deal_id="pepper:rel-wl",
            target_price=2500,
            created_at="2026-04-13T10:00:00",
        )
        session.add(wl)
        session.commit()

        loaded = session.get(Deal, "pepper:rel-wl")
        assert loaded.watchlist_entry is not None
        assert loaded.watchlist_entry.target_price == 2500


class TestSeenDealModel:
    def test_create_seen_deal(self, session):
        seen = SeenDeal(
            deal_id="pepper:789",
            profile="bikes",
            dedup_key="test bike|5000",
            first_seen_at="2026-04-13T10:00:00",
        )
        session.add(seen)
        session.commit()

        result = session.query(SeenDeal).filter_by(deal_id="pepper:789").first()
        assert result is not None
        assert result.profile == "bikes"
        assert result.dedup_key == "test bike|5000"


class TestFeedbackModel:
    def _make_deal(self, session, deal_id: str) -> Deal:
        deal = Deal(
            id=deal_id,
            raw_title="Feedback Test Deal",
            current_price_pln=1500,
            url="https://example.com",
            source="pepper",
            description="",
            image_url="",
            profile="bikes",
            score=50,
            category="",
            status="active",
            first_seen_at="2026-04-13T10:00:00",
            last_seen_at="2026-04-13T10:00:00",
        )
        session.add(deal)
        session.flush()
        return deal

    def test_create_feedback(self, session):
        self._make_deal(session, "pepper:fb-1")
        fb = Feedback(
            deal_id="pepper:fb-1",
            action="watch",
            created_at="2026-04-13T12:00:00",
        )
        session.add(fb)
        session.commit()

        result = session.get(Feedback, ("pepper:fb-1", "2026-04-13T12:00:00"))
        assert result is not None
        assert result.action == "watch"

    def test_feedback_round_trip(self, session):
        self._make_deal(session, "pepper:fb-2")
        fb = Feedback(
            deal_id="pepper:fb-2",
            action="skip",
            created_at="2026-04-13T13:00:00",
        )
        session.add(fb)
        session.commit()
        session.expire_all()

        reloaded = session.get(Feedback, ("pepper:fb-2", "2026-04-13T13:00:00"))
        assert reloaded.deal_id == "pepper:fb-2"
        assert reloaded.action == "skip"
        assert reloaded.created_at == "2026-04-13T13:00:00"

    def test_feedback_null_action(self, session):
        self._make_deal(session, "pepper:fb-3")
        fb = Feedback(deal_id="pepper:fb-3", created_at="2026-04-13T14:00:00")
        session.add(fb)
        session.commit()

        result = session.get(Feedback, ("pepper:fb-3", "2026-04-13T14:00:00"))
        assert result is not None
        assert result.action is None


class TestAlertQueueModel:
    def test_create_alert_queue(self, session):
        alert = AlertQueue(
            profile="bikes",
            alert_type="deal",
            payload='{"deal_id": "pepper:999"}',
            created_at="2026-04-13T22:00:00",
        )
        session.add(alert)
        session.commit()

        result = session.query(AlertQueue).filter_by(profile="bikes").first()
        assert result is not None
        assert result.alert_type == "deal"
        assert result.sent_at is None

    def test_alert_queue_round_trip(self, session):
        alert = AlertQueue(
            profile="nas",
            alert_type="price_drop",
            payload='{"drop": 500}',
            created_at="2026-04-13T23:00:00",
            sent_at=None,
        )
        session.add(alert)
        session.commit()
        alert_id = alert.id
        session.expire_all()

        reloaded = session.get(AlertQueue, alert_id)
        assert reloaded.profile == "nas"
        assert reloaded.alert_type == "price_drop"
        assert reloaded.payload == '{"drop": 500}'
        assert reloaded.sent_at is None

    def test_alert_queue_mark_sent(self, session):
        alert = AlertQueue(
            profile="bikes",
            alert_type="deal",
            payload="{}",
            created_at="2026-04-13T22:30:00",
        )
        session.add(alert)
        session.commit()

        alert.sent_at = "2026-04-13T23:59:00"
        session.commit()
        session.expire_all()

        reloaded = session.get(AlertQueue, alert.id)
        assert reloaded.sent_at == "2026-04-13T23:59:00"

    def test_alert_queue_autoincrement_id(self, session):
        a1 = AlertQueue(
            profile="p1",
            alert_type="deal",
            payload="{}",
            created_at="2026-04-13T10:00:00",
        )
        a2 = AlertQueue(
            profile="p2",
            alert_type="deal",
            payload="{}",
            created_at="2026-04-13T11:00:00",
        )
        session.add_all([a1, a2])
        session.commit()
        assert a1.id != a2.id


class TestWatchlistItemModel:
    def _make_deal(self, session, deal_id: str) -> Deal:
        deal = Deal(
            id=deal_id,
            raw_title="Watchlist Test Deal",
            current_price_pln=4000,
            url="https://example.com",
            source="pepper",
            description="",
            image_url="",
            profile="bikes",
            score=65,
            category="",
            status="active",
            first_seen_at="2026-04-13T10:00:00",
            last_seen_at="2026-04-13T10:00:00",
        )
        session.add(deal)
        session.flush()
        return deal

    def test_create_watchlist_item(self, session):
        self._make_deal(session, "pepper:wl-1")
        item = WatchlistItem(
            deal_id="pepper:wl-1",
            target_price=3500,
            created_at="2026-04-13T10:00:00",
        )
        session.add(item)
        session.commit()

        result = session.query(WatchlistItem).filter_by(deal_id="pepper:wl-1").first()
        assert result is not None
        assert result.target_price == 3500
        assert result.triggered_at is None

    def test_watchlist_item_round_trip(self, session):
        self._make_deal(session, "pepper:wl-2")
        item = WatchlistItem(
            deal_id="pepper:wl-2",
            target_price=2999,
            created_at="2026-04-13T11:00:00",
        )
        session.add(item)
        session.commit()
        item_id = item.id
        session.expire_all()

        reloaded = session.get(WatchlistItem, item_id)
        assert reloaded.deal_id == "pepper:wl-2"
        assert reloaded.target_price == 2999
        assert reloaded.created_at == "2026-04-13T11:00:00"

    def test_watchlist_item_mark_triggered(self, session):
        self._make_deal(session, "pepper:wl-3")
        item = WatchlistItem(
            deal_id="pepper:wl-3",
            target_price=1500,
            created_at="2026-04-13T09:00:00",
        )
        session.add(item)
        session.commit()

        item.triggered_at = "2026-04-13T15:00:00"
        session.commit()
        session.expire_all()

        reloaded = session.get(WatchlistItem, item.id)
        assert reloaded.triggered_at == "2026-04-13T15:00:00"

    def test_watchlist_item_unique_deal_id(self, session):
        """deal_id has a UNIQUE constraint — second insert must fail."""
        import sqlalchemy.exc

        self._make_deal(session, "pepper:wl-4")
        item1 = WatchlistItem(
            deal_id="pepper:wl-4",
            target_price=1000,
            created_at="2026-04-13T10:00:00",
        )
        session.add(item1)
        session.commit()

        item2 = WatchlistItem(
            deal_id="pepper:wl-4",
            target_price=900,
            created_at="2026-04-13T11:00:00",
        )
        session.add(item2)
        with pytest.raises(sqlalchemy.exc.IntegrityError):
            session.commit()


class TestIndexes:
    def test_deals_index_exists(self, engine):
        indexes = {idx["name"] for idx in inspect(engine).get_indexes("offers")}
        assert "idx_offers_profile_score" in indexes

    def test_deals_index_columns(self, engine):
        indexes = inspect(engine).get_indexes("offers")
        idx = next(i for i in indexes if i["name"] == "idx_offers_profile_score")
        assert set(idx["column_names"]) == {"profile", "score"}

    def test_seen_deals_index_exists(self, engine):
        indexes = {idx["name"] for idx in inspect(engine).get_indexes("seen_deals")}
        assert "idx_seen_deals_profile_deal" in indexes

    def test_seen_deals_index_columns(self, engine):
        indexes = inspect(engine).get_indexes("seen_deals")
        idx = next(i for i in indexes if i["name"] == "idx_seen_deals_profile_deal")
        assert set(idx["column_names"]) == {"profile", "deal_id"}
