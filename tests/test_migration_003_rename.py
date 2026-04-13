"""Round-trip test for Alembic revision 003_rename_deals_to_offers."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


@pytest.fixture
def alembic_db(tmp_path: Path) -> tuple[Config, str]:
    """Fresh SQLite DB with a pre-wired Alembic config pointing to it."""
    db_url = f"sqlite:///{tmp_path / 'test.db'}"
    cfg = Config("storage/migrations/alembic.ini")
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg, db_url


def _table_names(db_url: str) -> set[str]:
    eng = create_engine(db_url)
    return set(inspect(eng).get_table_names())


def test_003_upgrade_renames_tables(alembic_db, monkeypatch):
    cfg, db_url = alembic_db
    monkeypatch.setenv("DATABASE_URL", db_url)
    command.upgrade(cfg, "002")
    assert {"deals", "price_history"} <= _table_names(db_url)
    assert "offers" not in _table_names(db_url)

    command.upgrade(cfg, "003")
    tables = _table_names(db_url)
    assert "offers" in tables
    assert "price_points" in tables
    assert "deals" not in tables
    assert "price_history" not in tables


def test_003_downgrade_restores_tables(alembic_db, monkeypatch):
    cfg, db_url = alembic_db
    monkeypatch.setenv("DATABASE_URL", db_url)
    command.upgrade(cfg, "003")
    command.downgrade(cfg, "002")
    tables = _table_names(db_url)
    assert "deals" in tables
    assert "price_history" in tables
    assert "offers" not in tables
    assert "price_points" not in tables


def test_003_roundtrip_preserves_row_data(alembic_db, monkeypatch):
    """Upgrade, insert a row, downgrade, upgrade again — data survives the final upgrade."""
    from sqlalchemy import text

    cfg, db_url = alembic_db
    monkeypatch.setenv("DATABASE_URL", db_url)
    command.upgrade(cfg, "002")

    eng = create_engine(db_url)
    with eng.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO deals"
                " (id, title, price, source, status, first_seen, last_seen)"
                " VALUES"
                " ('pepper:abc', 'Test', 100, 'pepper', 'active', '2026-01-01', '2026-01-01')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO price_history (deal_id, price, recorded_at)"
                " VALUES ('pepper:abc', 100, '2026-01-01')"
            )
        )

    command.upgrade(cfg, "003")

    with eng.connect() as conn:
        row = conn.execute(text("SELECT id, title FROM offers WHERE id='pepper:abc'")).first()
        assert row is not None
        assert row[1] == "Test"
        pp = conn.execute(
            text("SELECT deal_id, price FROM price_points WHERE deal_id='pepper:abc'")
        ).first()
        assert pp is not None
        assert pp[1] == 100
