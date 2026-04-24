"""Round-trip + backfill test for Alembic revision 005_offer_callback_token."""

import hashlib
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


def _indexes(db_url: str, table: str) -> set[str]:
    eng = create_engine(db_url)
    try:
        return {idx["name"] for idx in inspect(eng).get_indexes(table)}
    finally:
        eng.dispose()


def test_005_adds_callback_token_column_and_index(alembic_db, monkeypatch):
    cfg, db_url = alembic_db
    monkeypatch.setenv("DATABASE_URL", db_url)
    command.upgrade(cfg, "005")
    assert "callback_token" in _columns(db_url, "offers")
    assert "ix_offers_callback_token" in _indexes(db_url, "offers")


def test_005_backfills_tokens_for_existing_rows(alembic_db, monkeypatch):
    cfg, db_url = alembic_db
    monkeypatch.setenv("DATABASE_URL", db_url)

    # Insert rows before 005 runs (at revision 004, offers is reachable).
    command.upgrade(cfg, "004")
    eng = create_engine(db_url)
    with eng.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO offers (id, raw_title, source, status,"
                " first_seen_at, last_seen_at)"
                " VALUES ('pepper:seed1', 't', 'pepper', 'active',"
                " '2026-01-01', '2026-01-01')"
            )
        )
    eng.dispose()

    command.upgrade(cfg, "005")

    eng = create_engine(db_url)
    with eng.connect() as conn:
        row = conn.execute(
            text("SELECT callback_token FROM offers WHERE id = 'pepper:seed1'")
        ).one()
    eng.dispose()

    expected = hashlib.blake2s(b"pepper:seed1", digest_size=8).hexdigest()
    assert row[0] == expected


def test_005_roundtrip_upgrade_downgrade_upgrade(alembic_db, monkeypatch):
    cfg, db_url = alembic_db
    monkeypatch.setenv("DATABASE_URL", db_url)
    command.upgrade(cfg, "005")
    assert "callback_token" in _columns(db_url, "offers")

    command.downgrade(cfg, "004")
    assert "callback_token" not in _columns(db_url, "offers")

    command.upgrade(cfg, "005")
    assert "callback_token" in _columns(db_url, "offers")
