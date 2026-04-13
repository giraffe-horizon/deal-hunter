"""Tests for database session management."""

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from storage.database import SessionLocal, engine, get_session
from storage.models import Base, Deal


@pytest.fixture(autouse=True)
def _setup_tables():
    """Create tables for each test, drop after."""
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


class TestEngine:
    def test_engine_connects(self):
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            assert result.scalar() == 1

    def test_wal_mode_enabled(self):
        with engine.connect() as conn:
            mode = conn.execute(text("PRAGMA journal_mode")).scalar()
            assert mode == "wal"


class TestGetSession:
    def test_yields_session(self):
        with get_session() as session:
            assert isinstance(session, Session)

    def test_auto_commits_on_success(self):
        with get_session() as session:
            deal = Deal(
                id="test:1",
                title="Test",
                price=100,
                source="test",
                description="",
                image_url="",
                profile="test",
                score=50,
                status="active",
                first_seen="2026-04-13",
                last_seen="2026-04-13",
            )
            session.add(deal)

        with get_session() as session:
            loaded = session.get(Deal, "test:1")
            assert loaded is not None
            assert loaded.title == "Test"

    def test_auto_rollback_on_exception(self):
        with pytest.raises(ValueError, match="boom"), get_session() as session:
            deal = Deal(
                id="test:2",
                title="Fail",
                price=0,
                source="test",
                description="",
                image_url="",
                profile="test",
                score=0,
                status="active",
                first_seen="2026-04-13",
                last_seen="2026-04-13",
            )
            session.add(deal)
            session.flush()
            raise ValueError("boom")

        with get_session() as session:
            assert session.get(Deal, "test:2") is None


class TestSessionLocal:
    def test_creates_session(self):
        session = SessionLocal()
        assert isinstance(session, Session)
        session.close()
