"""Feedback repository — user feedback actions (watch / skip / open) on deals."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from deal_hunter.storage.models import Feedback


class FeedbackRepository:
    """Query and mutation wrapper for feedback table."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def record(self, deal_id: str, action: str) -> None:
        """Record user feedback on a deal."""
        fb = Feedback(
            deal_id=deal_id,
            action=action,
            created_at=datetime.now().isoformat(),
        )
        self.session.add(fb)

    def record_many(self, ids: list[str], action: str) -> int:
        """Record the same feedback action for many deal ids. Returns rows inserted."""
        if not ids:
            return 0
        now = datetime.now().isoformat()
        self.session.bulk_insert_mappings(
            Feedback,
            [{"deal_id": deal_id, "action": action, "created_at": now} for deal_id in ids],
        )
        return len(ids)

    def get_stats(self) -> dict[str, int]:
        """Get counts of feedback actions."""
        rows = self.session.execute(
            select(Feedback.action, func.count().label("cnt")).group_by(Feedback.action)
        ).all()
        return {row[0]: row[1] for row in rows}
