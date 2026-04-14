"""Round-trip + backfill test for Alembic revision 004_products_schema."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


@pytest.fixture
def alembic_db(tmp_path: Path) -> tuple[Config, str]:
    db_url = f"sqlite:///{tmp_path / 'test.db'}"
    cfg = Config("src/deal_hunter/storage/migrations/alembic.ini")
    return cfg, db_url


def _columns(db_url: str, table: str) -> set[str]:
    eng = create_engine(db_url)
    try:
        return {c["name"] for c in inspect(eng).get_columns(table)}
    finally:
        eng.dispose()


def _tables(db_url: str) -> set[str]:
    eng = create_engine(db_url)
    try:
        return set(inspect(eng).get_table_names())
    finally:
        eng.dispose()


def test_004_upgrade_renames_offer_columns(alembic_db, monkeypatch):
    cfg, db_url = alembic_db
    monkeypatch.setenv("DATABASE_URL", db_url)
    command.upgrade(cfg, "004")
    cols = _columns(db_url, "offers")
    assert {"raw_title", "current_price_pln", "url", "first_seen_at", "last_seen_at"} <= cols
    assert {"title", "price", "link", "first_seen", "last_seen"}.isdisjoint(cols)


def test_004_upgrade_renames_pricepoint_columns(alembic_db, monkeypatch):
    cfg, db_url = alembic_db
    monkeypatch.setenv("DATABASE_URL", db_url)
    command.upgrade(cfg, "004")
    cols = _columns(db_url, "price_points")
    assert {"offer_id", "price_pln", "recorded_at"} <= cols
    assert "deal_id" not in cols
    assert "price" not in cols or "price_pln" in cols  # only price_pln, not bare price


def test_004_adds_new_offer_columns(alembic_db, monkeypatch):
    cfg, db_url = alembic_db
    monkeypatch.setenv("DATABASE_URL", db_url)
    command.upgrade(cfg, "004")
    cols = _columns(db_url, "offers")
    assert {
        "product_id",
        "source_native_id",
        "current_price_original",
        "currency_original",
        "fx_rate_used",
        "availability",
        "attributes_hint",
        "is_active",
    } <= cols


def test_004_adds_new_pricepoint_columns(alembic_db, monkeypatch):
    cfg, db_url = alembic_db
    monkeypatch.setenv("DATABASE_URL", db_url)
    command.upgrade(cfg, "004")
    cols = _columns(db_url, "price_points")
    assert {
        "product_id",
        "price_original",
        "currency_original",
        "fx_rate_used",
        "availability",
    } <= cols


def test_004_creates_new_tables(alembic_db, monkeypatch):
    cfg, db_url = alembic_db
    monkeypatch.setenv("DATABASE_URL", db_url)
    command.upgrade(cfg, "004")
    tables = _tables(db_url)
    assert {
        "products",
        "product_aliases",
        "offer_payload_history",
        "deal_events",
        "match_reviews",
        "match_decisions",
        "fx_rates",
    } <= tables


def test_004_backfills_source_native_id(alembic_db, monkeypatch):
    cfg, db_url = alembic_db
    monkeypatch.setenv("DATABASE_URL", db_url)
    command.upgrade(cfg, "003")
    eng = create_engine(db_url)
    with eng.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO offers (id, title, price, source, status,"
                " first_seen, last_seen)"
                " VALUES ('pepper:abc123', 't', 100, 'pepper', 'active',"
                " '2026-01-01', '2026-01-01')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO offers (id, title, source, status,"
                " first_seen, last_seen)"
                " VALUES ('proshop:9#size=54', 't', 'proshop', 'active',"
                " '2026-01-01', '2026-01-01')"
            )
        )
    command.upgrade(cfg, "004")
    with eng.connect() as conn:
        rows = dict(conn.execute(text("SELECT id, source_native_id FROM offers")).all())
    assert rows["pepper:abc123"] == "abc123"
    assert rows["proshop:9#size=54"] == "9#size=54"
    eng.dispose()


def test_004_roundtrip_upgrade_downgrade_upgrade(alembic_db, monkeypatch):
    cfg, db_url = alembic_db
    monkeypatch.setenv("DATABASE_URL", db_url)
    command.upgrade(cfg, "004")
    assert {"products", "deal_events"} <= _tables(db_url)

    command.downgrade(cfg, "003")
    tables_after_down = _tables(db_url)
    assert "products" not in tables_after_down
    assert "deal_events" not in tables_after_down
    assert "offers" in tables_after_down  # 003 survives
    cols_after_down = _columns(db_url, "offers")
    assert "raw_title" not in cols_after_down
    assert "title" in cols_after_down

    command.upgrade(cfg, "004")
    assert {"products", "deal_events"} <= _tables(db_url)
