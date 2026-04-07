"""Tests for batch query methods in SQLiteStorage."""

from storage.sqlite import SQLiteStorage


def test_get_price_histories_batch(tmp_path):
    db = SQLiteStorage(tmp_path / "test.db")
    try:
        from sources.base import Deal

        deal1 = Deal(id="test:1", title="Deal 1", price=100, link="", source="test",
                     description="", temperature=0, image_url="", published_at="")
        deal2 = Deal(id="test:2", title="Deal 2", price=200, link="", source="test",
                     description="", temperature=0, image_url="", published_at="")
        db.upsert_deal(deal1, "test_profile", 50)
        db.upsert_deal(deal2, "test_profile", 60)

        db.record_price("test:1", 100)
        db.record_price("test:1", 90)
        db.record_price("test:2", 200)

        result = db.get_price_histories_batch(["test:1", "test:2", "test:nonexistent"])

        assert "test:1" in result
        assert "test:2" in result
        assert "test:nonexistent" in result
        assert len(result["test:1"]) == 3  # 1 from upsert + 2 from record_price
        assert len(result["test:2"]) == 2  # 1 from upsert + 1 from record_price
        assert len(result["test:nonexistent"]) == 0
    finally:
        db.close()


def test_get_price_histories_batch_empty(tmp_path):
    db = SQLiteStorage(tmp_path / "test.db")
    try:
        result = db.get_price_histories_batch([])
        assert result == {}
    finally:
        db.close()


def test_get_lowest_prices_batch(tmp_path):
    db = SQLiteStorage(tmp_path / "test.db")
    try:
        from sources.base import Deal

        deal1 = Deal(id="test:1", title="Deal 1", price=100, link="", source="test",
                     description="", temperature=0, image_url="", published_at="")
        db.upsert_deal(deal1, "test_profile", 50)
        db.record_price("test:1", 100)
        db.record_price("test:1", 80)
        db.record_price("test:1", 90)

        result = db.get_lowest_prices_batch(["test:1", "test:nonexistent"])
        assert result["test:1"] == 80
        assert result["test:nonexistent"] is None
    finally:
        db.close()
