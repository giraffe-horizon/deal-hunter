"""Alert queue repository — queued Telegram alerts during quiet hours."""

from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from deal_hunter.storage.models import AlertQueue


class AlertQueueRepository:
    """Query and mutation wrapper for alert_queue table."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def queue(self, profile: str, alert_type: str, payload_json: str) -> None:
        """Queue an alert for later sending."""
        alert = AlertQueue(
            profile=profile,
            alert_type=alert_type,
            payload=payload_json,
            created_at=datetime.now().isoformat(),
        )
        self.session.add(alert)

    def get_pending(self, profile: str | None = None) -> list[dict]:
        """Get unsent alerts, ordered by creation time."""
        stmt = select(AlertQueue).where(AlertQueue.sent_at.is_(None))
        if profile is not None:
            stmt = stmt.where(AlertQueue.profile == profile)
        stmt = stmt.order_by(AlertQueue.created_at.asc())
        return [
            {
                "id": a.id,
                "profile": a.profile,
                "alert_type": a.alert_type,
                "payload": a.payload,
                "created_at": a.created_at,
            }
            for a in self.session.scalars(stmt)
        ]

    def mark_sent(self, alert_ids: list[int]) -> None:
        """Mark alerts as sent."""
        if not alert_ids:
            return
        now = datetime.now().isoformat()
        self.session.execute(
            text(
                f"UPDATE alert_queue SET sent_at = :now"  # noqa: S608
                f" WHERE id IN ({','.join(f':id_{i}' for i in range(len(alert_ids)))})"
            ),
            {"now": now, **{f"id_{i}": aid for i, aid in enumerate(alert_ids)}},
        )
