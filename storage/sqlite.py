"""SQLite persistence layer for Deal Hunter."""

import logging
import sqlite3
from datetime import datetime, timedelta
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

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

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
        except sqlite3.Error as e:
            logger.error(f"Failed to record price for {deal_id}: {e}")

    def get_deals(
        self,
        profile: str | None = None,
        source: str | None = None,
        min_score: int | None = None,
        category: str | None = None,
        status: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[dict]:
        """Query deals with optional filters and pagination."""
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

        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
            if offset is not None:
                query += " OFFSET ?"
                params.append(offset)

        try:
            rows = self._conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Failed to query deals: {e}")
            return []

    def count_deals(
        self,
        profile: str | None = None,
        source: str | None = None,
        min_score: int | None = None,
        category: str | None = None,
        status: str | None = None,
    ) -> int:
        """Count deals matching filters."""
        query = "SELECT COUNT(*) as cnt FROM deals WHERE 1=1"
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

        try:
            row = self._conn.execute(query, params).fetchone()
            return int(row["cnt"]) if row else 0
        except sqlite3.Error as e:
            logger.error(f"Failed to count deals: {e}")
            return 0

    def get_deal_stats(self, score_threshold: int = 70) -> dict:
        """Get aggregate deal statistics via SQL."""
        today = datetime.now().strftime("%Y-%m-%d")
        try:
            row = self._conn.execute(
                """SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN score >= ? THEN 1 ELSE 0 END) as high_score,
                    SUM(CASE WHEN first_seen LIKE ? THEN 1 ELSE 0 END) as new_today
                FROM deals""",
                (score_threshold, f"{today}%"),
            ).fetchone()
            return dict(row) if row else {"total": 0, "high_score": 0, "new_today": 0}
        except sqlite3.Error as e:
            logger.error(f"Failed to get deal stats: {e}")
            return {"total": 0, "high_score": 0, "new_today": 0}

    def get_filter_options(self) -> dict:
        """Get distinct sources and categories for filter dropdowns."""
        try:
            sources = self._conn.execute(
                "SELECT DISTINCT source FROM deals WHERE source IS NOT NULL AND source != '' ORDER BY source"
            ).fetchall()
            categories = self._conn.execute(
                "SELECT DISTINCT category FROM deals WHERE category IS NOT NULL AND category != '' ORDER BY category"
            ).fetchall()
            return {
                "sources": [r["source"] for r in sources],
                "categories": [r["category"] for r in categories],
            }
        except sqlite3.Error as e:
            logger.error(f"Failed to get filter options: {e}")
            return {"sources": [], "categories": []}

    def get_category_price_trend(self, category: str, days: int = 30) -> list[dict]:
        """Get daily average price for a category over the last N days."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        try:
            rows = self._conn.execute(
                """SELECT DATE(ph.recorded_at) as day, AVG(ph.price) as avg_price
                FROM price_history ph
                JOIN deals d ON ph.deal_id = d.id
                WHERE d.category = ? AND ph.recorded_at >= ?
                GROUP BY DATE(ph.recorded_at)
                ORDER BY day""",
                (category, cutoff),
            ).fetchall()
            return [{"day": r["day"], "avg_price": round(r["avg_price"])} for r in rows]
        except sqlite3.Error as e:
            logger.error(f"Failed to get category trend for {category}: {e}")
            return []

    def get_deal(self, deal_id: str) -> dict | None:
        """Get a single deal by ID."""
        try:
            row = self._conn.execute("SELECT * FROM deals WHERE id = ?", (deal_id,)).fetchone()
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

    def import_legacy_deal(
        self,
        deal_id: str,
        title: str,
        price: int,
        source: str,
        profile: str,
        first_seen: str,
        last_seen: str,
    ) -> None:
        """Import a deal from legacy state files. Used by the migration script."""
        try:
            self._conn.execute(
                """INSERT INTO deals (id, title, price, link, source, description,
                   image_url, profile, score, category, first_seen, last_seen, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                   last_seen = MAX(deals.last_seen, excluded.last_seen)""",
                (
                    deal_id,
                    title,
                    price,
                    "",
                    source,
                    "",
                    "",
                    profile,
                    0,
                    "",
                    first_seen,
                    last_seen,
                    "active",
                ),
            )
        except sqlite3.Error as e:
            logger.error(f"Failed to import legacy deal {deal_id}: {e}")

    def import_legacy_price(
        self,
        deal_id: str,
        price: int,
        recorded_at: str,
    ) -> None:
        """Import a price history entry from legacy state files."""
        try:
            self._conn.execute(
                "INSERT OR IGNORE INTO price_history (deal_id, price, recorded_at) VALUES (?, ?, ?)",
                (deal_id, price, recorded_at),
            )
        except sqlite3.Error as e:
            logger.error(f"Failed to import legacy price for {deal_id}: {e}")

    def get_lowest_price(self, deal_id: str) -> int | None:
        """Get the lowest price ever recorded for a deal."""
        try:
            row = self._conn.execute(
                "SELECT MIN(price) as min_price FROM price_history WHERE deal_id = ?",
                (deal_id,),
            ).fetchone()
            return row["min_price"] if row and row["min_price"] is not None else None
        except sqlite3.Error as e:
            logger.error(f"Failed to get lowest price for {deal_id}: {e}")
            return None

    def get_previous_price(self, deal_id: str) -> int | None:
        """Get the most recent price before the current one."""
        try:
            rows = self._conn.execute(
                "SELECT price FROM price_history WHERE deal_id = ? ORDER BY recorded_at DESC LIMIT 2",
                (deal_id,),
            ).fetchall()
            # rows[0] is current, rows[1] is previous
            if len(rows) >= 2:
                return int(rows[1]["price"])
            return None
        except sqlite3.Error as e:
            logger.error(f"Failed to get previous price for {deal_id}: {e}")
            return None

    def get_price_drops(
        self,
        profile: str | None = None,
        days: int = 7,
        min_drop_percent: float = 0,
    ) -> list[dict]:
        """Get deals that had price drops in the last N days.

        Returns list of dicts with deal info + drop details.
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        try:
            # Find deals where a newer price_history entry is lower than an older one
            query = """
                SELECT d.*, ph_new.price as new_price, ph_new.recorded_at as drop_date
                FROM deals d
                JOIN price_history ph_new ON d.id = ph_new.deal_id
                WHERE ph_new.recorded_at >= ?
            """
            params: list = [cutoff]

            if profile is not None:
                query += " AND d.profile = ?"
                params.append(profile)

            query += " ORDER BY ph_new.recorded_at DESC"

            rows = self._conn.execute(query, params).fetchall()

            results = []
            seen_deals: set[str] = set()
            for row in rows:
                deal_id = row["id"]
                if deal_id in seen_deals:
                    continue

                new_price = row["new_price"]
                # Get the price entry just before this one
                prev = self._conn.execute(
                    """SELECT price FROM price_history
                       WHERE deal_id = ? AND recorded_at < ?
                       ORDER BY recorded_at DESC LIMIT 1""",
                    (deal_id, row["drop_date"]),
                ).fetchone()

                if not prev or prev["price"] <= new_price:
                    continue

                old_price = prev["price"]
                diff_pln = old_price - new_price
                diff_percent = (diff_pln / old_price) * 100 if old_price > 0 else 0

                if diff_percent < min_drop_percent:
                    continue

                lowest = self.get_lowest_price(deal_id)
                is_lowest = lowest is not None and new_price <= lowest

                seen_deals.add(deal_id)
                results.append(
                    {
                        **dict(row),
                        "old_price": old_price,
                        "new_price": new_price,
                        "diff_pln": diff_pln,
                        "diff_percent": round(diff_percent, 1),
                        "is_lowest_ever": is_lowest,
                    }
                )

            return results
        except sqlite3.Error as e:
            logger.error(f"Failed to get price drops: {e}")
            return []

    def update_deal_status(self, deal_id: str, status: str) -> bool:
        """Update a deal's status. Returns True if the deal existed."""
        try:
            cursor = self._conn.execute(
                "UPDATE deals SET status = ? WHERE id = ?", (status, deal_id)
            )
            self._conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Failed to update status for {deal_id}: {e}")
            return False

    def get_deals_by_status(self, status: str, limit: int = 20) -> list[dict]:
        """Get deals filtered by status, ordered by last_seen descending."""
        try:
            rows = self._conn.execute(
                "SELECT * FROM deals WHERE status = ? ORDER BY last_seen DESC LIMIT ?",
                (status, limit),
            ).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Failed to get deals by status '{status}': {e}")
            return []

    def get_feedback_stats(self) -> dict:
        """Get counts of feedback actions. Returns {'watch': N, 'skip': M, ...}."""
        try:
            rows = self._conn.execute(
                "SELECT action, COUNT(*) as cnt FROM feedback GROUP BY action"
            ).fetchall()
            return {row["action"]: row["cnt"] for row in rows}
        except sqlite3.Error as e:
            logger.error(f"Failed to get feedback stats: {e}")
            return {}

    def commit(self) -> None:
        """Commit the current transaction."""
        self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        try:
            self._conn.close()
        except sqlite3.Error as e:
            logger.debug(f"Error closing database: {e}")
