"""FIFO retention test for OfferPayloadHistory."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from storage.models import Base, Offer, OfferPayloadHistory
from storage.repositories import OfferPayloadHistoryRepository


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        now = datetime.now().isoformat()
        s.add(
            Offer(
                id="pepper:1",
                raw_title="t",
                source="pepper",
                first_seen_at=now,
                last_seen_at=now,
            )
        )
        s.commit()
        yield s


def test_append_keeps_newest_ten(session: Session) -> None:
    repo = OfferPayloadHistoryRepository(session)
    base = datetime(2026, 1, 1)
    for i in range(15):
        ts = (base + timedelta(minutes=i)).isoformat()
        repo.append(offer_id="pepper:1", raw_payload={"seq": i}, captured_at=ts)
    session.commit()

    rows = (
        session.execute(
            select(OfferPayloadHistory)
            .where(OfferPayloadHistory.offer_id == "pepper:1")
            .order_by(OfferPayloadHistory.captured_at.asc())
        )
        .scalars()
        .all()
    )
    assert len(rows) == 10
    assert rows[0].raw_payload == {"seq": 5}
    assert rows[-1].raw_payload == {"seq": 14}


def test_append_per_offer_isolated(session: Session) -> None:
    now = datetime.now().isoformat()
    session.add(
        Offer(
            id="pepper:2",
            raw_title="t2",
            source="pepper",
            first_seen_at=now,
            last_seen_at=now,
        )
    )
    session.commit()
    repo = OfferPayloadHistoryRepository(session)
    for i in range(12):
        repo.append(offer_id="pepper:1", raw_payload={"x": i}, captured_at=f"t-{i:02d}")
    for i in range(3):
        repo.append(offer_id="pepper:2", raw_payload={"y": i}, captured_at=f"u-{i:02d}")
    session.commit()

    assert session.query(OfferPayloadHistory).filter_by(offer_id="pepper:1").count() == 10
    assert session.query(OfferPayloadHistory).filter_by(offer_id="pepper:2").count() == 3
