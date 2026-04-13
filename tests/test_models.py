"""Tests for SQLAlchemy ORM models."""

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from storage.models import (
    Base,
    Deal,
    PriceHistory,
    SeenDeal,
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
            "deals",
            "price_history",
            "feedback",
            "alert_queue",
            "watchlist",
            "seen_deals",
        }

    def test_deals_columns(self, engine):
        cols = {c["name"] for c in inspect(engine).get_columns("deals")}
        assert cols == {
            "id",
            "title",
            "price",
            "link",
            "source",
            "description",
            "image_url",
            "profile",
            "score",
            "category",
            "status",
            "first_seen",
            "last_seen",
        }

    def test_seen_deals_columns(self, engine):
        cols = {c["name"] for c in inspect(engine).get_columns("seen_deals")}
        assert cols == {"id", "deal_id", "profile", "dedup_key", "first_seen_at"}


class TestDealModel:
    def test_create_deal(self, session):
        deal = Deal(
            id="pepper:123",
            title="Test Deal",
            price=1000,
            link="https://example.com",
            source="pepper",
            description="desc",
            image_url="",
            profile="bikes",
            score=80,
            category="road",
            status="active",
            first_seen="2026-04-13T10:00:00",
            last_seen="2026-04-13T10:00:00",
        )
        session.add(deal)
        session.commit()

        loaded = session.get(Deal, "pepper:123")
        assert loaded is not None
        assert loaded.title == "Test Deal"
        assert loaded.price == 1000
        assert loaded.status == "active"

    def test_deal_relationships(self, session):
        deal = Deal(
            id="pepper:456",
            title="Bike",
            price=5000,
            link="https://example.com",
            source="pepper",
            description="",
            image_url="",
            profile="bikes",
            score=70,
            category="",
            status="active",
            first_seen="2026-04-13T10:00:00",
            last_seen="2026-04-13T10:00:00",
        )
        session.add(deal)
        session.flush()

        ph = PriceHistory(deal_id="pepper:456", price=5000, recorded_at="2026-04-13T10:00:00")
        session.add(ph)
        session.commit()

        loaded = session.get(Deal, "pepper:456")
        assert len(loaded.prices) == 1
        assert loaded.prices[0].price == 5000


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
