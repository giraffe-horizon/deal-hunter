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
