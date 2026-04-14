"""OfferPayloadHistory repository — append-with-eviction raw scrape payloads per offer."""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from deal_hunter.storage.models import OfferPayloadHistory

OFFER_PAYLOAD_HISTORY_MAX = 10


class OfferPayloadHistoryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def append(self, *, offer_id: str, raw_payload: dict, captured_at: str) -> OfferPayloadHistory:
        row = OfferPayloadHistory(
            offer_id=offer_id, raw_payload=raw_payload, captured_at=captured_at
        )
        self.session.add(row)
        self.session.flush()
        self._evict_beyond_limit(offer_id)
        return row

    def _evict_beyond_limit(self, offer_id: str) -> None:
        subq = (
            select(OfferPayloadHistory.id)
            .where(OfferPayloadHistory.offer_id == offer_id)
            .order_by(OfferPayloadHistory.captured_at.desc())
            .offset(OFFER_PAYLOAD_HISTORY_MAX)
        )
        ids_to_delete = list(self.session.execute(subq).scalars().all())
        if ids_to_delete:
            self.session.execute(
                delete(OfferPayloadHistory).where(OfferPayloadHistory.id.in_(ids_to_delete))
            )
