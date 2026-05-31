"""Sent-notifications repository — persistent dispatch history."""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from deal_hunter.storage.models import SentNotification


class SentNotificationRepository:
    """Query and mutation wrapper for sent_notifications."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def record(
        self,
        *,
        alert_type: str,
        payload_json: str,
        deal_id: str | None = None,
        profile: str | None = None,
        sent_at: str | None = None,
    ) -> None:
        """Insert a row. Caller commits via the session."""
        row = SentNotification(
            alert_type=alert_type,
            deal_id=deal_id,
            profile=profile,
            payload=payload_json,
            sent_at=sent_at or datetime.now().isoformat(),
        )
        self.session.add(row)

    def last_sent_at(self, deal_id: str, alert_type: str) -> str | None:
        """MAX(sent_at) for the given deal + alert_type, or None."""
        stmt = select(func.max(SentNotification.sent_at)).where(
            SentNotification.deal_id == deal_id,
            SentNotification.alert_type == alert_type,
        )
        return self.session.execute(stmt).scalar()

    def list_recent(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        alert_type: str | None = None,
        profile: str | None = None,
        since: str | None = None,
    ) -> list[dict]:
        """Return rows newest-first, with payload JSON-decoded."""
        stmt = select(SentNotification).order_by(SentNotification.sent_at.desc())
        if alert_type is not None:
            stmt = stmt.where(SentNotification.alert_type == alert_type)
        if profile is not None:
            stmt = stmt.where(SentNotification.profile == profile)
        if since is not None:
            stmt = stmt.where(SentNotification.sent_at >= since)
        stmt = stmt.limit(limit).offset(offset)
        return [self._to_dict(r) for r in self.session.scalars(stmt)]

    def count(
        self,
        *,
        alert_type: str | None = None,
        profile: str | None = None,
        since: str | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(SentNotification)
        if alert_type is not None:
            stmt = stmt.where(SentNotification.alert_type == alert_type)
        if profile is not None:
            stmt = stmt.where(SentNotification.profile == profile)
        if since is not None:
            stmt = stmt.where(SentNotification.sent_at >= since)
        return self.session.execute(stmt).scalar() or 0

    @staticmethod
    def _to_dict(row: SentNotification) -> dict:
        try:
            payload = json.loads(row.payload)
        except (TypeError, ValueError):
            payload = {"_raw": row.payload}
        return {
            "id": row.id,
            "alert_type": row.alert_type,
            "deal_id": row.deal_id,
            "profile": row.profile,
            "payload": payload,
            "sent_at": row.sent_at,
        }
