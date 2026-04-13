"""Tests for repository layer."""

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.models import Base, Deal, PriceHistory
from storage.repositories import DealRepository


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


def _make_deal(**overrides):
    """Helper to build Deal kwargs with defaults."""
    defaults = {
        "id": "pepper:123",
        "title": "Test Bike",
        "price": 5000,
        "link": "https://example.com",
        "source": "pepper",
        "description": "A test deal",
        "image_url": "",
        "profile": "bikes",
        "score": 80,
        "category": "road",
        "status": "active",
        "first_seen": datetime.now().isoformat(),
        "last_seen": datetime.now().isoformat(),
    }
    defaults.update(overrides)
    return defaults


class TestDealRepositoryUpsert:
    def test_insert_new_deal(self, session, deal_repo):
        deal_repo.upsert(**_make_deal())
        session.flush()
        loaded = session.get(Deal, "pepper:123")
        assert loaded is not None
        assert loaded.title == "Test Bike"
        assert loaded.score == 80

    def test_update_existing_deal(self, session, deal_repo):
        deal_repo.upsert(**_make_deal())
        session.flush()
        deal_repo.upsert(**_make_deal(score=90, price=4500))
        session.flush()
        loaded = session.get(Deal, "pepper:123")
        assert loaded.score == 90
        assert loaded.price == 4500

    def test_upsert_preserves_status(self, session, deal_repo):
        """Upsert must NOT reset status to 'active' on update."""
        deal_repo.upsert(**_make_deal())
        session.flush()
        loaded = session.get(Deal, "pepper:123")
        loaded.status = "watching"
        session.flush()
        deal_repo.upsert(**_make_deal(score=90))
        session.flush()
        loaded = session.get(Deal, "pepper:123")
        assert loaded.status == "watching"

    def test_upsert_records_initial_price(self, session, deal_repo):
        deal_repo.upsert(**_make_deal(price=5000))
        session.flush()
        prices = session.query(PriceHistory).filter_by(deal_id="pepper:123").all()
        assert len(prices) == 1
        assert prices[0].price == 5000

    def test_upsert_records_price_change(self, session, deal_repo):
        deal_repo.upsert(**_make_deal(price=5000))
        session.flush()
        deal_repo.upsert(**_make_deal(price=4500))
        session.flush()
        prices = session.query(PriceHistory).filter_by(deal_id="pepper:123").all()
        assert len(prices) == 2

    def test_upsert_no_price_no_history(self, session, deal_repo):
        deal_repo.upsert(**_make_deal(price=0))
        session.flush()
        prices = session.query(PriceHistory).filter_by(deal_id="pepper:123").all()
        assert len(prices) == 0


class TestDealRepositoryQuery:
    @pytest.fixture(autouse=True)
    def _seed(self, session, deal_repo):
        deal_repo.upsert(
            **_make_deal(
                id="pepper:1",
                title="Bike A",
                score=90,
                profile="bikes",
                source="pepper",
                category="road",
            )
        )
        deal_repo.upsert(
            **_make_deal(
                id="ceneo:2",
                title="HDD B",
                score=60,
                profile="nas_hdd",
                source="ceneo",
                category="storage",
            )
        )
        deal_repo.upsert(
            **_make_deal(
                id="pepper:3",
                title="Bike C",
                score=40,
                profile="bikes",
                source="pepper",
                category="mtb",
            )
        )
        session.flush()

    def test_get_by_id(self, deal_repo):
        deal = deal_repo.get_by_id("pepper:1")
        assert deal is not None
        assert deal["title"] == "Bike A"

    def test_get_by_id_not_found(self, deal_repo):
        assert deal_repo.get_by_id("nope:0") is None

    def test_get_filtered_by_profile(self, deal_repo):
        deals = deal_repo.get_filtered(profile="bikes")
        assert len(deals) == 2

    def test_get_filtered_by_source(self, deal_repo):
        deals = deal_repo.get_filtered(source="ceneo")
        assert len(deals) == 1

    def test_get_filtered_by_min_score(self, deal_repo):
        deals = deal_repo.get_filtered(min_score=80)
        assert len(deals) == 1

    def test_get_filtered_ordered_by_score_desc(self, deal_repo):
        deals = deal_repo.get_filtered()
        scores = [d["score"] for d in deals]
        assert scores == sorted(scores, reverse=True)

    def test_get_filtered_with_limit_offset(self, deal_repo):
        deals = deal_repo.get_filtered(limit=1, offset=1)
        assert len(deals) == 1
        assert deals[0]["score"] == 60  # second by score desc

    def test_get_by_ids(self, deal_repo):
        deals = deal_repo.get_by_ids(["pepper:1", "ceneo:2"])
        assert len(deals) == 2

    def test_get_by_ids_empty(self, deal_repo):
        assert deal_repo.get_by_ids([]) == []

    def test_count(self, deal_repo):
        assert deal_repo.count() == 3
        assert deal_repo.count(profile="bikes") == 2
        assert deal_repo.count(min_score=80) == 1

    def test_get_stats(self, deal_repo):
        stats = deal_repo.get_stats(score_threshold=70)
        assert stats["total"] == 3
        assert stats["high_score"] == 1  # score >= 70: only 90

    def test_update_status(self, session, deal_repo):
        assert deal_repo.update_status("pepper:1", "watching") is True
        session.flush()
        deal = deal_repo.get_by_id("pepper:1")
        assert deal["status"] == "watching"

    def test_update_status_not_found(self, deal_repo):
        assert deal_repo.update_status("nope:0", "watching") is False

    def test_get_filter_options(self, deal_repo):
        opts = deal_repo.get_filter_options()
        assert "pepper" in opts["sources"]
        assert "ceneo" in opts["sources"]
        assert "road" in opts["categories"]

    def test_get_by_status(self, session, deal_repo):
        deal = session.get(Deal, "pepper:1")
        deal.status = "watching"
        session.flush()
        result = deal_repo.get_by_status("watching")
        assert len(result) == 1
        assert result[0]["id"] == "pepper:1"
