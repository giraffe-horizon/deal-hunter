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

    def get_stats(self) -> dict[str, int]:
        """Get counts of feedback actions."""
        rows = self.session.execute(
            select(Feedback.action, func.count().label("cnt")).group_by(Feedback.action)
        ).all()
        return {row[0]: row[1] for row in rows}
