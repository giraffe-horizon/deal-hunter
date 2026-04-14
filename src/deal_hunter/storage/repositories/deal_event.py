"""DealEvent repository — emits + tracks deal-lifecycle events for downstream notifiers."""

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from deal_hunter.storage.models import DealEvent


class DealEventRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def emit(
        self,
        *,
        offer_id: str,
        event_type: str,
        price_at_event: int | None = None,
        payload: dict | None = None,
        product_id: str | None = None,
        created_at: str | None = None,
    ) -> DealEvent:
        evt = DealEvent(
            offer_id=offer_id,
            product_id=product_id,
            event_type=event_type,
            price_at_event=price_at_event,
            payload=payload,
            created_at=created_at or datetime.now().isoformat(),
        )
        self.session.add(evt)
        self.session.flush()
        return evt

    def get_unnotified(self, limit: int = 50) -> list[DealEvent]:
        return list(
            self.session.execute(
                select(DealEvent)
                .where(DealEvent.notified == 0)
                .order_by(DealEvent.created_at.asc())
                .limit(limit)
            ).scalars()
        )

    def mark_notified(self, ids: list[int]) -> None:
        if not ids:
            return
        self.session.execute(update(DealEvent).where(DealEvent.id.in_(ids)).values(notified=1))
