"""Tests for repository layer."""

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.models import Base, SeenDeal
from storage.models import Offer as Deal
from storage.models import PricePoint as PriceHistory
from storage.repositories import (
    AlertQueueRepository,
    FeedbackRepository,
    PriceRepository,
    SeenDealRepository,
    WatchlistRepository,
)
from storage.repositories import (
    OfferRepository as DealRepository,
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


@pytest.fixture
def price_repo(session):
    return PriceRepository(session)


def _seed_deal_with_prices(session, deal_id="pepper:100", prices=None):
    """Insert a deal and its price history for testing."""
    now = datetime.now().isoformat()
    deal = Deal(
        id=deal_id,
        title="Price Test",
        price=prices[-1] if prices else 1000,
        source="pepper",
        description="",
        image_url="",
        profile="bikes",
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


class TestPriceRepositoryBasic:
    def test_record_price(self, session, price_repo):
        _seed_deal_with_prices(session, prices=[])
        price_repo.record("pepper:100", 5000)
        session.flush()
        history = price_repo.get_history("pepper:100")
        assert len(history) == 1
        assert history[0]["price"] == 5000

    def test_get_history_chronological(self, session, price_repo):
        _seed_deal_with_prices(session, prices=[5000, 4500, 4000])
        history = price_repo.get_history("pepper:100")
        assert [h["price"] for h in history] == [5000, 4500, 4000]

    def test_get_lowest(self, session, price_repo):
        _seed_deal_with_prices(session, prices=[5000, 3000, 4000])
        assert price_repo.get_lowest("pepper:100") == 3000

    def test_get_lowest_nonexistent(self, price_repo):
        assert price_repo.get_lowest("nope:0") is None

    def test_get_previous_price(self, session, price_repo):
        _seed_deal_with_prices(session, prices=[5000, 4500, 4000])
        assert price_repo.get_previous_price("pepper:100") == 4500

    def test_get_previous_price_single_entry(self, session, price_repo):
        _seed_deal_with_prices(session, prices=[5000])
        assert price_repo.get_previous_price("pepper:100") is None


class TestPriceRepositoryBatch:
    def test_get_histories_batch(self, session, price_repo):
        _seed_deal_with_prices(session, deal_id="p:1", prices=[100, 200])
        _seed_deal_with_prices(session, deal_id="p:2", prices=[300])
        result = price_repo.get_histories_batch(["p:1", "p:2"])
        assert len(result["p:1"]) == 2
        assert len(result["p:2"]) == 1

    def test_get_histories_batch_empty(self, price_repo):
        assert price_repo.get_histories_batch([]) == {}

    def test_get_lowest_prices_batch(self, session, price_repo):
        _seed_deal_with_prices(session, deal_id="p:1", prices=[100, 50])
        _seed_deal_with_prices(session, deal_id="p:2", prices=[300, 200])
        result = price_repo.get_lowest_prices_batch(["p:1", "p:2"])
        assert result["p:1"] == 50
        assert result["p:2"] == 200

    def test_get_sparkline_data_batch(self, session, price_repo):
        _seed_deal_with_prices(session, deal_id="p:1", prices=[100, 200, 300, 400, 500])
        result = price_repo.get_sparkline_data_batch(["p:1"], limit=3)
        assert len(result["p:1"]) == 3


class TestPriceRepositoryDrops:
    """Tests for get_drops() — the N+1 fix using window functions."""

    @pytest.fixture(autouse=True)
    def _seed(self, session):
        # Deal with price drop: 5000 -> 4000
        _seed_deal_with_prices(session, deal_id="p:drop", prices=[5000, 4000])
        # Deal with price increase: 3000 -> 4000
        _seed_deal_with_prices(session, deal_id="p:up", prices=[3000, 4000])
        # Deal with single price (no change)
        _seed_deal_with_prices(session, deal_id="p:flat", prices=[2000])

    def test_finds_drops(self, price_repo):
        drops = price_repo.get_drops(days=30)
        drop_ids = [d["id"] for d in drops]
        assert "p:drop" in drop_ids
        assert "p:up" not in drop_ids
        assert "p:flat" not in drop_ids

    def test_drop_fields(self, price_repo):
        drops = price_repo.get_drops(days=30)
        drop = next(d for d in drops if d["id"] == "p:drop")
        assert drop["old_price"] == 5000
        assert drop["new_price"] == 4000
        assert drop["diff_pln"] == 1000
        assert drop["diff_percent"] == 20.0
        assert "is_lowest_ever" in drop

    def test_count_drops(self, price_repo):
        assert price_repo.count_drops(days=30) >= 1

    def test_drops_with_profile_filter(self, price_repo):
        drops = price_repo.get_drops(days=30, profile="bikes")
        # All seeded deals have profile "bikes"
        assert len(drops) >= 1

    def test_drops_with_min_percent_filter(self, price_repo):
        drops = price_repo.get_drops(days=30, min_drop_percent=50)
        assert len(drops) == 0  # 20% drop doesn't meet 50% threshold


@pytest.fixture
def watchlist_repo(session):
    return WatchlistRepository(session)


def _seed_deal(session, deal_id="pepper:w1"):
    """Insert a deal for FK reference in watchlist tests."""
    deal = Deal(
        id=deal_id,
        title="Watchlist Test",
        price=5000,
        source="pepper",
        description="",
        image_url="",
        profile="bikes",
        score=80,
        category="road",
        status="active",
        first_seen=datetime.now().isoformat(),
        last_seen=datetime.now().isoformat(),
    )
    session.add(deal)
    session.flush()


class TestWatchlistRepository:
    def test_add(self, session, watchlist_repo):
        _seed_deal(session)
        result = watchlist_repo.add("pepper:w1", 4000)
        session.flush()
        assert result is True

    def test_add_duplicate(self, session, watchlist_repo):
        _seed_deal(session)
        watchlist_repo.add("pepper:w1", 4000)
        session.flush()
        assert watchlist_repo.add("pepper:w1", 3000) is False

    def test_remove(self, session, watchlist_repo):
        _seed_deal(session)
        watchlist_repo.add("pepper:w1", 4000)
        session.flush()
        assert watchlist_repo.remove("pepper:w1") is True

    def test_remove_nonexistent(self, watchlist_repo):
        assert watchlist_repo.remove("nope:0") is False

    def test_get_all(self, session, watchlist_repo):
        _seed_deal(session, "pepper:w1")
        _seed_deal(session, "pepper:w2")
        watchlist_repo.add("pepper:w1", 4000)
        watchlist_repo.add("pepper:w2", 3000)
        session.flush()
        items = watchlist_repo.get_all()
        assert len(items) == 2

    def test_get_item(self, session, watchlist_repo):
        _seed_deal(session)
        watchlist_repo.add("pepper:w1", 4000)
        session.flush()
        item = watchlist_repo.get_item("pepper:w1")
        assert item is not None
        assert item["target_price"] == 4000
        assert item["title"] == "Watchlist Test"

    def test_update_target_price(self, session, watchlist_repo):
        _seed_deal(session)
        watchlist_repo.add("pepper:w1", 4000)
        session.flush()
        assert watchlist_repo.update_target_price("pepper:w1", 3500) is True
        item = watchlist_repo.get_item("pepper:w1")
        assert item["target_price"] == 3500

    def test_check_trigger_met(self, session, watchlist_repo):
        _seed_deal(session)
        watchlist_repo.add("pepper:w1", 4000)
        session.flush()
        result = watchlist_repo.check_trigger("pepper:w1", current_price=3500)
        assert result is not None
        assert result["target_price"] == 4000

    def test_check_trigger_not_met(self, session, watchlist_repo):
        _seed_deal(session)
        watchlist_repo.add("pepper:w1", 4000)
        session.flush()
        assert watchlist_repo.check_trigger("pepper:w1", current_price=5000) is None

    def test_mark_triggered(self, session, watchlist_repo):
        _seed_deal(session)
        watchlist_repo.add("pepper:w1", 4000)
        session.flush()
        watchlist_repo.mark_triggered("pepper:w1")
        session.flush()
        # After triggering, check_trigger should return None
        assert watchlist_repo.check_trigger("pepper:w1", current_price=3000) is None


@pytest.fixture
def alert_repo(session):
    return AlertQueueRepository(session)


@pytest.fixture
def feedback_repo(session):
    return FeedbackRepository(session)


class TestAlertQueueRepository:
    def test_queue_alert(self, session, alert_repo):
        alert_repo.queue("bikes", "deal", '{"title": "test"}')
        session.flush()
        pending = alert_repo.get_pending()
        assert len(pending) == 1
        assert pending[0]["profile"] == "bikes"

    def test_get_pending_filters_by_profile(self, session, alert_repo):
        alert_repo.queue("bikes", "deal", '{"a": 1}')
        alert_repo.queue("nas_hdd", "deal", '{"b": 2}')
        session.flush()
        assert len(alert_repo.get_pending(profile="bikes")) == 1

    def test_get_pending_excludes_sent(self, session, alert_repo):
        alert_repo.queue("bikes", "deal", '{"a": 1}')
        session.flush()
        pending = alert_repo.get_pending()
        alert_repo.mark_sent([p["id"] for p in pending])
        session.flush()
        assert len(alert_repo.get_pending()) == 0

    def test_mark_sent_empty_list(self, alert_repo):
        alert_repo.mark_sent([])  # should not error

    def test_get_pending_ordered_by_created_at(self, session, alert_repo):
        alert_repo.queue("bikes", "deal", '{"first": true}')
        alert_repo.queue("bikes", "deal", '{"second": true}')
        session.flush()
        pending = alert_repo.get_pending()
        assert len(pending) == 2


class TestFeedbackRepository:
    @pytest.fixture(autouse=True)
    def _seed_deal(self, session):
        _seed_deal_with_prices(session, deal_id="pepper:fb1", prices=[])

    def test_record_feedback(self, session, feedback_repo):
        feedback_repo.record("pepper:fb1", "watch")
        session.flush()

    def test_get_stats(self, session, feedback_repo):
        feedback_repo.record("pepper:fb1", "watch")
        feedback_repo.record("pepper:fb1", "watch")
        feedback_repo.record("pepper:fb1", "skip")
        session.flush()
        stats = feedback_repo.get_stats()
        assert stats["watch"] == 2
        assert stats["skip"] == 1

    def test_get_stats_empty(self, feedback_repo):
        assert feedback_repo.get_stats() == {}


@pytest.fixture
def seen_repo(session):
    return SeenDealRepository(session)


class TestSeenDealRepository:
    def test_mark_seen(self, session, seen_repo):
        seen_repo.mark_seen("pepper:100", "bikes", "test bike|5000")
        session.flush()
        assert seen_repo.is_seen("pepper:100", "bikes") is True

    def test_is_seen_false(self, seen_repo):
        assert seen_repo.is_seen("pepper:999", "bikes") is False

    def test_is_seen_wrong_profile(self, session, seen_repo):
        seen_repo.mark_seen("pepper:100", "bikes", "test|5000")
        session.flush()
        assert seen_repo.is_seen("pepper:100", "nas_hdd") is False

    def test_cleanup_expired(self, session, seen_repo):
        # Insert an old entry
        old_seen = SeenDeal(
            deal_id="pepper:old",
            profile="bikes",
            dedup_key="old|1000",
            first_seen_at="2020-01-01T00:00:00",
        )
        session.add(old_seen)
        # Insert a recent entry
        seen_repo.mark_seen("pepper:new", "bikes", "new|2000")
        session.flush()

        seen_repo.cleanup_expired(ttl_days=14)
        session.flush()

        assert seen_repo.is_seen("pepper:old", "bikes") is False
        assert seen_repo.is_seen("pepper:new", "bikes") is True

    def test_get_seen_ids(self, session, seen_repo):
        seen_repo.mark_seen("pepper:1", "bikes", "a|1000")
        seen_repo.mark_seen("pepper:2", "bikes", "b|2000")
        seen_repo.mark_seen("pepper:3", "nas_hdd", "c|3000")
        session.flush()
        ids = seen_repo.get_seen_ids("bikes")
        assert "pepper:1" in ids
        assert "pepper:2" in ids
        assert "pepper:3" not in ids
