"""Round-trip test for Alembic revision 007_sent_notifications."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


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


def _tables(db_url: str) -> set[str]:
    eng = create_engine(db_url)
    try:
        return set(inspect(eng).get_table_names())
    finally:
        eng.dispose()


def test_007_creates_sent_notifications_table(alembic_db, monkeypatch):
    cfg, db_url = alembic_db
    monkeypatch.setenv("DATABASE_URL", db_url)
    command.upgrade(cfg, "007")
    assert "sent_notifications" in _tables(db_url)
    cols = _columns(db_url, "sent_notifications")
    assert cols == {"id", "alert_type", "deal_id", "profile", "payload", "sent_at"}


def test_007_creates_indexes(alembic_db, monkeypatch):
    cfg, db_url = alembic_db
    monkeypatch.setenv("DATABASE_URL", db_url)
    command.upgrade(cfg, "007")
    idx = _indexes(db_url, "sent_notifications")
    assert "ix_sent_notifications_deal_id_alert_type" in idx
    assert "ix_sent_notifications_sent_at" in idx


def test_007_downgrade_drops_table(alembic_db, monkeypatch):
    cfg, db_url = alembic_db
    monkeypatch.setenv("DATABASE_URL", db_url)
    command.upgrade(cfg, "007")
    command.downgrade(cfg, "006")
    assert "sent_notifications" not in _tables(db_url)
