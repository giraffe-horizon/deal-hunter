"""Tests for DealEvent repository."""

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.models import Base, Offer
from storage.repositories import DealEventRepository


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        now = datetime.now().isoformat()
        s.add(
            Offer(
                id="pepper:10",
                raw_title="t",
                source="pepper",
                first_seen_at=now,
                last_seen_at=now,
            )
        )
        s.commit()
        yield s


def test_emit_new_listing(session: Session) -> None:
    repo = DealEventRepository(session)
    evt = repo.emit(
        offer_id="pepper:10",
        event_type="new_listing",
        price_at_event=100,
        payload={"first_price": 100},
    )
    session.commit()
    assert evt.id is not None
    assert evt.notified == 0


def test_get_unnotified(session: Session) -> None:
    repo = DealEventRepository(session)
    e1 = repo.emit(offer_id="pepper:10", event_type="new_listing", price_at_event=100)
    e2 = repo.emit(offer_id="pepper:10", event_type="price_drop", price_at_event=80)
    session.commit()
    unread = repo.get_unnotified(limit=10)
    assert {e.id for e in unread} == {e1.id, e2.id}

    repo.mark_notified([e1.id])
    session.commit()
    unread_again = repo.get_unnotified(limit=10)
    assert {e.id for e in unread_again} == {e2.id}
