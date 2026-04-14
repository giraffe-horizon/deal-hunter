"""SQLAlchemy engine and session management for Deal Hunter."""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

_BASE_DIR = Path(__file__).resolve().parents[3]
_DEFAULT_DB = f"sqlite:///{_BASE_DIR / 'state' / 'deals.db'}"
DATABASE_URL = os.environ.get("DATABASE_URL", _DEFAULT_DB)

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
