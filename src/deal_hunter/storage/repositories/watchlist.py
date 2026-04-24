"""Watchlist repository — user-defined target-price watches."""

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from deal_hunter.storage.models import WatchlistItem


class WatchlistRepository:
    """Query and mutation wrapper for watchlist table."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, deal_id: str, target_price: int) -> bool:
        """Add a deal to watchlist. Returns False if already exists."""
        existing = self.session.query(WatchlistItem).filter_by(deal_id=deal_id).first()
        if existing:
            return False
        item = WatchlistItem(
            deal_id=deal_id,
            target_price=target_price,
            created_at=datetime.now().isoformat(),
        )
        self.session.add(item)
        return True

    def remove(self, deal_id: str) -> bool:
        """Remove from watchlist. Returns True if found and removed."""
        item = self.session.query(WatchlistItem).filter_by(deal_id=deal_id).first()
        if not item:
            return False
        self.session.delete(item)
        return True

    def get_all(self) -> list[dict]:
        """Get all watchlist items with deal info."""
        rows = (
            self.session.execute(
                text(
                    """SELECT w.deal_id, w.target_price, w.created_at, w.triggered_at,
                          d.raw_title AS title, d.current_price_pln AS current_price,
                          d.url AS link, d.source
                   FROM watchlist w
                   LEFT JOIN offers d ON w.deal_id = d.id
                   ORDER BY w.created_at DESC"""
                )
            )
            .mappings()
            .all()
        )
        return [dict(r) for r in rows]

    def get_item(self, deal_id: str) -> dict | None:
        """Get a single watchlist item with deal info."""
        row = (
            self.session.execute(
                text(
                    """SELECT w.deal_id, w.target_price, w.created_at, w.triggered_at,
                          d.raw_title AS title, d.current_price_pln AS current_price,
                          d.url AS link, d.source
                   FROM watchlist w
                   LEFT JOIN offers d ON w.deal_id = d.id
                   WHERE w.deal_id = :deal_id"""
                ),
                {"deal_id": deal_id},
            )
            .mappings()
            .first()
        )
        return dict(row) if row else None

    def update_target_price(self, deal_id: str, target_price: int) -> bool:
        """Update target price. Returns True if found."""
        item = self.session.query(WatchlistItem).filter_by(deal_id=deal_id).first()
        if not item:
            return False
        item.target_price = target_price
        self.session.flush()
        return True

    def bulk_upsert(self, ids: list[str], target_price: int) -> int:
        """Insert or update watchlist entries for a list of deal ids."""
        if not ids:
            return 0
        now = datetime.now().isoformat()
        rows = [
            {"deal_id": deal_id, "target_price": target_price, "created_at": now} for deal_id in ids
        ]
        stmt = sqlite_insert(WatchlistItem).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=[WatchlistItem.deal_id],
            set_={"target_price": stmt.excluded.target_price},
        )
        self.session.execute(stmt)
        return len(rows)

    def check_trigger(self, deal_id: str, current_price: int) -> dict | None:
        """Check if current price meets watchlist target. Returns entry if triggered."""
        item = (
            self.session.query(WatchlistItem)
            .filter_by(deal_id=deal_id)
            .filter(WatchlistItem.triggered_at.is_(None))
            .first()
        )
        if item and current_price <= item.target_price:
            return {"deal_id": item.deal_id, "target_price": item.target_price}
        return None

    def mark_triggered(self, deal_id: str) -> None:
        """Mark a watchlist entry as triggered."""
        item = self.session.query(WatchlistItem).filter_by(deal_id=deal_id).first()
        if item:
            item.triggered_at = datetime.now().isoformat()
