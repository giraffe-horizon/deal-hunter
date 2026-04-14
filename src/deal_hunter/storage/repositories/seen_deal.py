"""Seen-deal repository — TTL-based cross-run deduplication (replaces JSON state)."""

from datetime import datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from deal_hunter.storage.models import SeenDeal


class SeenDealRepository:
    """Replaces JSON state files for seen-deal tracking."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def mark_seen(self, deal_id: str, profile: str, dedup_key: str) -> None:
        """Mark a deal as seen for a profile."""
        seen = SeenDeal(
            deal_id=deal_id,
            profile=profile,
            dedup_key=dedup_key,
            first_seen_at=datetime.now().isoformat(),
        )
        self.session.add(seen)

    def is_seen(self, deal_id: str, profile: str) -> bool:
        """Check if a deal has been seen for a profile (within TTL)."""
        cutoff = (datetime.now() - timedelta(days=14)).isoformat()
        result = (
            self.session.query(SeenDeal)
            .filter(
                SeenDeal.deal_id == deal_id,
                SeenDeal.profile == profile,
                SeenDeal.first_seen_at > cutoff,
            )
            .first()
        )
        return result is not None

    def get_seen_ids(self, profile: str) -> set[str]:
        """Get all seen deal IDs for a profile (within TTL)."""
        cutoff = (datetime.now() - timedelta(days=14)).isoformat()
        rows = (
            self.session.execute(
                select(SeenDeal.deal_id).where(
                    SeenDeal.profile == profile, SeenDeal.first_seen_at > cutoff
                )
            )
            .scalars()
            .all()
        )
        return set(rows)

    def cleanup_expired(self, ttl_days: int = 14) -> int:
        """Delete entries older than TTL. Returns count deleted."""
        cutoff = (datetime.now() - timedelta(days=ttl_days)).isoformat()
        result = self.session.execute(
            text("DELETE FROM seen_deals WHERE first_seen_at <= :cutoff"),
            {"cutoff": cutoff},
        )
        return int(result.rowcount)  # type: ignore[attr-defined]
