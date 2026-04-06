"""Tests for SQLite storage layer."""

import pytest

from sources.base import Deal
from storage.sqlite import SQLiteStorage


@pytest.fixture
def db(tmp_path):
    """Create a temporary SQLite database."""
    storage = SQLiteStorage(tmp_path / "test.db")
    yield storage
    storage.close()


@pytest.fixture
def deal():
    return Deal(
        id="pepper:99999",
        title="Test Deal Carbon Bike XL",
        price=8500,
        link="https://example.com/deal/99999",
        source="pepper",
        description="A great carbon bike with Shimano 105",
        temperature=120,
        image_url="https://example.com/img.jpg",
        published_at="2026-04-01T10:00:00",
    )


@pytest.fixture
def deal2():
    return Deal(
        id="ceneo:88888",
        title="NAS HDD Seagate IronWolf 8TB",
        price=1200,
        link="https://ceneo.pl/88888",
        source="ceneo",
        description="Seagate IronWolf 8TB NAS HDD",
        temperature=0,
        image_url="https://example.com/hdd.jpg",
        published_at="2026-04-02T12:00:00",
    )


class TestSQLiteStorageInit:
    def test_creates_db_file(self, tmp_path):
        db_path = tmp_path / "subdir" / "test.db"
        storage = SQLiteStorage(db_path)
        assert db_path.exists()
        storage.close()

    def test_creates_tables(self, db):
        tables = db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = [t["name"] for t in tables]
        assert "deals" in names
        assert "price_history" in names
        assert "feedback" in names

    def test_idempotent_init(self, tmp_path):
        db_path = tmp_path / "test.db"
        s1 = SQLiteStorage(db_path)
        s1.close()
        s2 = SQLiteStorage(db_path)
        s2.close()


class TestUpsertDeal:
    def test_insert_new_deal(self, db, deal):
        db.upsert_deal(deal, "bikes", 150)
        row = db.get_deal("pepper:99999")
        assert row is not None
        assert row["title"] == "Test Deal Carbon Bike XL"
        assert row["price"] == 8500
        assert row["source"] == "pepper"
        assert row["profile"] == "bikes"
        assert row["score"] == 150
        assert row["status"] == "active"

    def test_insert_with_category(self, db, deal):
        db.upsert_deal(deal, "bikes", 150, category="road")
        row = db.get_deal("pepper:99999")
        assert row["category"] == "road"

    def test_update_existing_deal(self, db, deal):
        db.upsert_deal(deal, "bikes", 100)
        first = db.get_deal("pepper:99999")

        # Update with higher score
        db.upsert_deal(deal, "bikes", 200)
        updated = db.get_deal("pepper:99999")

        assert updated["score"] == 200
        assert updated["last_seen"] >= first["last_seen"]

    def test_update_records_price_change(self, db, deal):
        db.upsert_deal(deal, "bikes", 100)

        # Change price
        deal.price = 7000
        db.upsert_deal(deal, "bikes", 100)

        history = db.get_price_history("pepper:99999")
        # Initial insert + price change = 2 entries
        assert len(history) == 2
        prices = [h["price"] for h in history]
        assert 8500 in prices
        assert 7000 in prices

    def test_upsert_no_price_no_history(self, db):
        deal = Deal(
            id="web:nopr",
            title="Free item",
            price=0,
            link="https://example.com",
            source="web",
            description="",
            temperature=0,
            image_url="",
            published_at="",
        )
        db.upsert_deal(deal, "test", 50)
        history = db.get_price_history("web:nopr")
        assert len(history) == 0


class TestRecordPrice:
    def test_record_price(self, db, deal):
        db.upsert_deal(deal, "bikes", 100)
        db.record_price("pepper:99999", 7500)
        db.record_price("pepper:99999", 7000)

        history = db.get_price_history("pepper:99999")
        # Initial from upsert + 2 manual = 3
        assert len(history) == 3

    def test_duplicate_timestamp_ignored(self, db, deal):
        db.upsert_deal(deal, "bikes", 100)
        # Same timestamp = same primary key -> INSERT OR IGNORE
        db._conn.execute(
            "INSERT OR IGNORE INTO price_history (deal_id, price, recorded_at) VALUES (?, ?, ?)",
            ("pepper:99999", 7000, "2026-04-01T10:00:00"),
        )
        db._conn.execute(
            "INSERT OR IGNORE INTO price_history (deal_id, price, recorded_at) VALUES (?, ?, ?)",
            ("pepper:99999", 6500, "2026-04-01T10:00:00"),
        )
        db._conn.commit()


class TestGetDeals:
    def test_get_all_deals(self, db, deal, deal2):
        db.upsert_deal(deal, "bikes", 150)
        db.upsert_deal(deal2, "nas_hdd", 80)
        results = db.get_deals()
        assert len(results) == 2

    def test_filter_by_profile(self, db, deal, deal2):
        db.upsert_deal(deal, "bikes", 150)
        db.upsert_deal(deal2, "nas_hdd", 80)
        results = db.get_deals(profile="bikes")
        assert len(results) == 1
        assert results[0]["id"] == "pepper:99999"

    def test_filter_by_source(self, db, deal, deal2):
        db.upsert_deal(deal, "bikes", 150)
        db.upsert_deal(deal2, "nas_hdd", 80)
        results = db.get_deals(source="ceneo")
        assert len(results) == 1
        assert results[0]["id"] == "ceneo:88888"

    def test_filter_by_min_score(self, db, deal, deal2):
        db.upsert_deal(deal, "bikes", 150)
        db.upsert_deal(deal2, "nas_hdd", 80)
        results = db.get_deals(min_score=100)
        assert len(results) == 1
        assert results[0]["score"] == 150

    def test_filter_by_category(self, db, deal, deal2):
        db.upsert_deal(deal, "bikes", 150, category="road")
        db.upsert_deal(deal2, "nas_hdd", 80, category="storage")
        results = db.get_deals(category="road")
        assert len(results) == 1

    def test_filter_by_status(self, db, deal):
        db.upsert_deal(deal, "bikes", 150)
        db._conn.execute("UPDATE deals SET status = 'rejected' WHERE id = ?", (deal.id,))
        db._conn.commit()
        assert len(db.get_deals(status="active")) == 0
        assert len(db.get_deals(status="rejected")) == 1

    def test_combined_filters(self, db, deal, deal2):
        db.upsert_deal(deal, "bikes", 150, category="road")
        db.upsert_deal(deal2, "bikes", 80, category="storage")
        results = db.get_deals(profile="bikes", min_score=100)
        assert len(results) == 1
        assert results[0]["id"] == "pepper:99999"

    def test_ordered_by_score_desc(self, db, deal, deal2):
        db.upsert_deal(deal, "bikes", 80)
        db.upsert_deal(deal2, "bikes", 150)
        results = db.get_deals()
        assert results[0]["score"] == 150
        assert results[1]["score"] == 80

    def test_empty_result(self, db):
        results = db.get_deals(profile="nonexistent")
        assert results == []


class TestGetDeal:
    def test_get_existing(self, db, deal):
        db.upsert_deal(deal, "bikes", 100)
        row = db.get_deal("pepper:99999")
        assert row is not None
        assert row["title"] == "Test Deal Carbon Bike XL"

    def test_get_nonexistent(self, db):
        assert db.get_deal("nonexistent:000") is None


class TestGetPriceHistory:
    def test_chronological_order(self, db, deal):
        db.upsert_deal(deal, "bikes", 100)
        db._conn.execute(
            "INSERT INTO price_history (deal_id, price, recorded_at) VALUES (?, ?, ?)",
            ("pepper:99999", 9000, "2026-03-01T00:00:00"),
        )
        db._conn.commit()
        # Should have: 2026-03-01 (manual), then the auto-recorded one from upsert
        history = db.get_price_history("pepper:99999")
        assert len(history) >= 2
        timestamps = [h["recorded_at"] for h in history]
        assert timestamps == sorted(timestamps)

    def test_empty_history(self, db):
        assert db.get_price_history("nonexistent:000") == []


class TestRecordFeedback:
    def test_record_feedback(self, db, deal):
        db.upsert_deal(deal, "bikes", 100)
        db.record_feedback("pepper:99999", "watch")
        db.record_feedback("pepper:99999", "skip")

        rows = db._conn.execute(
            "SELECT * FROM feedback WHERE deal_id = ? ORDER BY created_at",
            ("pepper:99999",),
        ).fetchall()
        assert len(rows) == 2
        assert rows[0]["action"] == "watch"
        assert rows[1]["action"] == "skip"

    def test_multiple_feedback_same_action(self, db, deal):
        db.upsert_deal(deal, "bikes", 100)
        db.record_feedback("pepper:99999", "open")
        db.record_feedback("pepper:99999", "open")

        rows = db._conn.execute(
            "SELECT COUNT(*) as cnt FROM feedback WHERE deal_id = ?",
            ("pepper:99999",),
        ).fetchone()
        assert rows["cnt"] == 2


class TestClose:
    def test_close(self, tmp_path):
        storage = SQLiteStorage(tmp_path / "test.db")
        storage.close()
        # Calling close again should not raise
        storage.close()


class TestCountDeals:
    def test_count_no_filters(self, db, deal, deal2):
        db.upsert_deal(deal, "bikes", 150)
        db.upsert_deal(deal2, "nas_hdd", 80)
        assert db.count_deals() == 2

    def test_count_with_profile_filter(self, db, deal, deal2):
        db.upsert_deal(deal, "bikes", 150)
        db.upsert_deal(deal2, "nas_hdd", 80)
        assert db.count_deals(profile="bikes") == 1

    def test_count_with_min_score_filter(self, db, deal, deal2):
        db.upsert_deal(deal, "bikes", 150)
        db.upsert_deal(deal2, "nas_hdd", 80)
        assert db.count_deals(min_score=100) == 1
        assert db.count_deals(min_score=80) == 2
        assert db.count_deals(min_score=200) == 0

    def test_count_with_multiple_filters(self, db, deal, deal2):
        db.upsert_deal(deal, "bikes", 150, category="road")
        db.upsert_deal(deal2, "bikes", 80, category="storage")
        assert db.count_deals(profile="bikes", min_score=100) == 1
        assert db.count_deals(profile="bikes", category="storage") == 1
        assert db.count_deals(source="pepper", min_score=100) == 1
        assert db.count_deals(source="ceneo", min_score=100) == 0

    def test_count_empty_db(self, db):
        assert db.count_deals() == 0


class TestGetDealStats:
    def test_returns_correct_stats(self, db, deal, deal2):
        from datetime import datetime

        deal.published_at = datetime.now().isoformat()
        db.upsert_deal(deal, "bikes", 150)
        db.upsert_deal(deal2, "nas_hdd", 80)

        stats = db.get_deal_stats(score_threshold=70)
        assert stats["total"] == 2
        assert stats["high_score"] == 2  # both >= 70
        assert stats["new_today"] >= 1  # deal was inserted today

    def test_custom_score_threshold(self, db, deal, deal2):
        db.upsert_deal(deal, "bikes", 150)
        db.upsert_deal(deal2, "nas_hdd", 80)

        stats_50 = db.get_deal_stats(score_threshold=50)
        stats_100 = db.get_deal_stats(score_threshold=100)
        assert stats_50["high_score"] == 2
        assert stats_100["high_score"] == 1

    def test_empty_db(self, db):
        stats = db.get_deal_stats()
        assert stats["total"] == 0
        # SUM on empty table returns None; verify no crash and falsy values
        assert not stats["high_score"]
        assert not stats["new_today"]

    def test_new_today_uses_today_date(self, db):
        from datetime import datetime

        # Insert a deal — first_seen is set automatically to now
        d = Deal(
            id="web:today1",
            title="Today Deal",
            price=100,
            link="https://example.com/today",
            source="web",
            description="inserted today",
            temperature=0,
            image_url="",
            published_at=datetime.now().isoformat(),
        )
        db.upsert_deal(d, "test", 50)

        # Insert old deal by manually setting first_seen in the past
        d2 = Deal(
            id="web:old1",
            title="Old Deal",
            price=200,
            link="https://example.com/old",
            source="web",
            description="old deal",
            temperature=0,
            image_url="",
            published_at="2025-01-01T00:00:00",
        )
        db.upsert_deal(d2, "test", 60)
        db._conn.execute(
            "UPDATE deals SET first_seen = ? WHERE id = ?",
            ("2025-01-01T00:00:00", "web:old1"),
        )
        db._conn.commit()

        stats = db.get_deal_stats()
        assert stats["total"] == 2
        assert stats["new_today"] == 1


class TestGetFilterOptions:
    def test_returns_distinct_sorted(self, db, deal, deal2):
        db.upsert_deal(deal, "bikes", 150, category="road")
        db.upsert_deal(deal2, "nas_hdd", 80, category="storage")
        opts = db.get_filter_options()
        assert opts["sources"] == ["ceneo", "pepper"]
        assert opts["categories"] == ["road", "storage"]

    def test_excludes_empty_strings(self, db, deal):
        db.upsert_deal(deal, "bikes", 150, category="")
        d2 = Deal(
            id="web:filt1",
            title="Filter Test",
            price=50,
            link="https://example.com",
            source="web",
            description="",
            temperature=0,
            image_url="",
            published_at="",
        )
        db.upsert_deal(d2, "test", 30, category="electronics")
        opts = db.get_filter_options()
        assert "" not in opts["categories"]
        assert "electronics" in opts["categories"]

    def test_empty_db(self, db):
        opts = db.get_filter_options()
        assert opts == {"sources": [], "categories": []}


class TestGetCategoryPriceTrend:
    def test_returns_daily_averages(self, db):
        from datetime import datetime

        d = Deal(
            id="web:trend1",
            title="Trend Deal A",
            price=1000,
            link="https://example.com/a",
            source="web",
            description="",
            temperature=0,
            image_url="",
            published_at="",
        )
        db.upsert_deal(d, "test", 50, category="gpu")

        # Add price history entries for today
        now = datetime.now().isoformat()
        db._conn.execute(
            "INSERT INTO price_history (deal_id, price, recorded_at) VALUES (?, ?, ?)",
            ("web:trend1", 900, now),
        )
        db._conn.commit()

        trend = db.get_category_price_trend("gpu", days=30)
        assert len(trend) >= 1
        assert "day" in trend[0]
        assert "avg_price" in trend[0]

    def test_empty_for_nonexistent_category(self, db):
        trend = db.get_category_price_trend("nonexistent", days=30)
        assert trend == []

    def test_respects_days_cutoff(self, db):
        d = Deal(
            id="web:trend2",
            title="Old Trend Deal",
            price=500,
            link="https://example.com/b",
            source="web",
            description="",
            temperature=0,
            image_url="",
            published_at="",
        )
        db.upsert_deal(d, "test", 50, category="cpu")

        # Add old price history (60 days ago)
        db._conn.execute(
            "INSERT INTO price_history (deal_id, price, recorded_at) VALUES (?, ?, ?)",
            ("web:trend2", 400, "2025-01-01T00:00:00"),
        )
        db._conn.commit()

        trend = db.get_category_price_trend("cpu", days=7)
        # The old entry should be excluded; only the upsert entry (today) should remain
        old_days = [t for t in trend if t["day"] == "2025-01-01"]
        assert len(old_days) == 0


class TestGetDealsWithPagination:
    def _insert_three_deals(self, db):
        deals = [
            Deal(
                id=f"web:pg{i}",
                title=f"Paginated Deal {i}",
                price=100 * i,
                link=f"https://example.com/{i}",
                source="web",
                description="",
                temperature=0,
                image_url="",
                published_at="",
            )
            for i in range(1, 4)
        ]
        for i, d in enumerate(deals):
            db.upsert_deal(d, "test", 100 + i * 10)
        return deals

    def test_limit_returns_subset(self, db):
        self._insert_three_deals(db)
        results = db.get_deals(limit=2)
        assert len(results) == 2

    def test_limit_with_offset(self, db):
        self._insert_three_deals(db)
        results = db.get_deals(limit=2, offset=2)
        assert len(results) == 1

    def test_no_limit_returns_all(self, db):
        self._insert_three_deals(db)
        results = db.get_deals()
        assert len(results) == 3
