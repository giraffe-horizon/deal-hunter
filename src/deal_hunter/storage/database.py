"""SQLAlchemy engine and session management for Deal Hunter."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from deal_hunter.core.settings import get_settings

DATABASE_URL = get_settings().default_database_url

# Ensure the database directory exists
_db_path = DATABASE_URL.replace("sqlite:///", "")
if _db_path:
    Path(_db_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn: Any, connection_record: Any) -> None:
    """Enable WAL mode and foreign keys for every new SQLite connection."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine)


@contextmanager
def get_session() -> Iterator[Session]:
    """Yield a transactional session. Commits on success, rolls back on error."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
