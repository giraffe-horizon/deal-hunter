"""Round-trip + backfill test for Alembic revision 006_notification_settings."""

import json
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


def test_006_adds_muted_until_to_offers(alembic_db, monkeypatch):
    cfg, db_url = alembic_db
    monkeypatch.setenv("DATABASE_URL", db_url)
    command.upgrade(cfg, "006")
    assert "muted_until" in _columns(db_url, "offers")
    assert "ix_offers_muted_until" in _indexes(db_url, "offers")


def test_006_adds_deal_id_to_alert_queue(alembic_db, monkeypatch):
    cfg, db_url = alembic_db
    monkeypatch.setenv("DATABASE_URL", db_url)
    command.upgrade(cfg, "006")
    assert "deal_id" in _columns(db_url, "alert_queue")
    assert "ix_alert_queue_deal_id" in _indexes(db_url, "alert_queue")


def test_006_backfills_deal_id_from_payload(alembic_db, monkeypatch):
    cfg, db_url = alembic_db
    monkeypatch.setenv("DATABASE_URL", db_url)

    command.upgrade(cfg, "005")
    eng = create_engine(db_url)
    payload = json.dumps({"deal_id": "pepper:42", "title": "x"})
    with eng.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO alert_queue (profile, alert_type, payload, created_at) "
                "VALUES (:p, :t, :pl, :c)"
            ),
            {"p": "bikes", "t": "price_drop", "pl": payload, "c": "2026-05-11T10:00:00"},
        )
    eng.dispose()

    command.upgrade(cfg, "006")

    eng = create_engine(db_url)
    with eng.begin() as conn:
        row = conn.execute(text("SELECT deal_id FROM alert_queue")).fetchone()
        assert row[0] == "pepper:42"
    eng.dispose()


def test_006_downgrade_removes_columns(alembic_db, monkeypatch):
    cfg, db_url = alembic_db
    monkeypatch.setenv("DATABASE_URL", db_url)
    command.upgrade(cfg, "006")
    command.downgrade(cfg, "005")
    assert "muted_until" not in _columns(db_url, "offers")
    assert "deal_id" not in _columns(db_url, "alert_queue")
