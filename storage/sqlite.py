"""SQLite persistence layer for Deal Hunter."""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS deals (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    price INTEGER,
    link TEXT,
    source TEXT,
    description TEXT,
    image_url TEXT,
    profile TEXT,
    score INTEGER,
    category TEXT,
    first_seen DATETIME,
    last_seen DATETIME,
    status TEXT DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS price_history (
    deal_id TEXT REFERENCES deals(id),
    price INTEGER,
    recorded_at DATETIME,
    PRIMARY KEY (deal_id, recorded_at)
);

CREATE TABLE IF NOT EXISTS feedback (
    deal_id TEXT REFERENCES deals(id),
    action TEXT,
    created_at DATETIME
);

CREATE INDEX IF NOT EXISTS idx_deals_profile_score ON deals(profile, score DESC);
"""


class SQLiteStorage:
    """SQLite-backed storage for deals, price history, and feedback."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
            )
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.executescript(SCHEMA_SQL)
            self._conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize SQLite database at {self.db_path}: {e}")
            raise

    def upsert_deal(
        self,
        deal,
        profile: str,
        score: int,
        category: str = "",
    ) -> None:
        """Insert a new deal or update last_seen and price if changed."""
        now = datetime.now().isoformat()
        try:
            existing = self._conn.execute(
                "SELECT id, price FROM deals WHERE id = ?", (deal.id,)
            ).fetchone()

            if existing:
                self._conn.execute(
                    """UPDATE deals
                       SET last_seen = ?, score = ?, price = ?, status = 'active'
                       WHERE id = ?""",
                    (now, score, deal.price, deal.id),
                )
                if existing["price"] and deal.price and existing["price"] != deal.price:
                    self.record_price(deal.id, deal.price)
            else:
                self._conn.execute(
                    """INSERT INTO deals
                       (id, title, price, link, source, description, image_url,
                        profile, score, category, first_seen, last_seen, status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')""",
                    (
                        deal.id,
                        deal.title,
                        deal.price,
                        deal.link,
                        deal.source,
                        deal.description,
                        deal.image_url,
                        profile,
                        score,
                        category,
                        now,
                        now,
                    ),
                )
                if deal.price:
                    self.record_price(deal.id, deal.price)

            self._conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to upsert deal {deal.id}: {e}")

    def record_price(self, deal_id: str, price: int) -> None:
        """Append a price entry to price_history."""
        now = datetime.now().isoformat()
        try:
            self._conn.execute(
                "INSERT OR IGNORE INTO price_history (deal_id, price, recorded_at) VALUES (?, ?, ?)",
                (deal_id, price, now),
            )
            self._conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to record price for {deal_id}: {e}")

    def get_deals(
        self,
        profile: str | None = None,
        source: str | None = None,
        min_score: int | None = None,
        category: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        """Query deals with optional filters."""
        query = "SELECT * FROM deals WHERE 1=1"
        params: list = []

        if profile is not None:
            query += " AND profile = ?"
            params.append(profile)
        if source is not None:
            query += " AND source = ?"
            params.append(source)
        if min_score is not None:
            query += " AND score >= ?"
            params.append(min_score)
        if category is not None:
            query += " AND category = ?"
            params.append(category)
        if status is not None:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY score DESC"

        try:
            rows = self._conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Failed to query deals: {e}")
            return []

    def get_deal(self, deal_id: str) -> dict | None:
        """Get a single deal by ID."""
        try:
            row = self._conn.execute(
                "SELECT * FROM deals WHERE id = ?", (deal_id,)
            ).fetchone()
            return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error(f"Failed to get deal {deal_id}: {e}")
            return None

    def get_price_history(self, deal_id: str) -> list[dict]:
        """Get price history for a deal, ordered chronologically."""
        try:
            rows = self._conn.execute(
                "SELECT * FROM price_history WHERE deal_id = ? ORDER BY recorded_at",
                (deal_id,),
            ).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Failed to get price history for {deal_id}: {e}")
            return []

    def record_feedback(self, deal_id: str, action: str) -> None:
        """Record user feedback on a deal."""
        now = datetime.now().isoformat()
        try:
            self._conn.execute(
                "INSERT INTO feedback (deal_id, action, created_at) VALUES (?, ?, ?)",
                (deal_id, action, now),
            )
            self._conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to record feedback for {deal_id}: {e}")

    def close(self) -> None:
        """Close the database connection."""
        try:
            self._conn.close()
        except sqlite3.Error:
            pass
