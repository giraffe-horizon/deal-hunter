"""Integration test: ingesting a fresh fetch appends payload history + emits events."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from services.fetcher import DealFetcher
from sources.base import Deal as FetchDTO
from storage.models import Base, DealEvent, OfferPayloadHistory


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_first_ingest_emits_new_listing_and_appends_payload(session: Session) -> None:
    dto = FetchDTO(
        id="pepper:111",
        title="Super deal",
        price=100,
        link="https://pepper.pl/111",
        source="pepper",
        description="d",
        temperature=42,
        image_url="",
        published_at="2026-01-01T00:00:00",
    )
    fetcher = DealFetcher(profile_name="bikes")
    fetcher.ingest_one(session, dto, profile={})
    session.commit()

    events = session.query(DealEvent).all()
    assert [e.event_type for e in events] == ["new_listing"]
    assert events[0].price_at_event == 100

    payloads = session.query(OfferPayloadHistory).all()
    assert len(payloads) == 1
    assert payloads[0].offer_id == "pepper:111"
    assert payloads[0].raw_payload["title"] == "Super deal"


def test_second_ingest_with_same_price_does_not_duplicate_event(session: Session) -> None:
    dto = FetchDTO(
        id="pepper:112",
        title="t",
        price=50,
        link="",
        source="pepper",
        description="",
        temperature=0,
        image_url="",
        published_at="",
    )
    fetcher = DealFetcher(profile_name="bikes")
    fetcher.ingest_one(session, dto, profile={})
    fetcher.ingest_one(session, dto, profile={})
    session.commit()
    events = session.query(DealEvent).all()
    assert [e.event_type for e in events] == ["new_listing"]
    assert session.query(OfferPayloadHistory).count() == 2


def test_reingest_with_lower_price_emits_price_drop(session: Session) -> None:
    fetcher = DealFetcher(profile_name="bikes")
    dto1 = FetchDTO(
        id="pepper:113",
        title="t",
        price=100,
        link="",
        source="pepper",
        description="",
        temperature=0,
        image_url="",
        published_at="",
    )
    fetcher.ingest_one(session, dto1, profile={})
    session.commit()
    dto2 = FetchDTO(
        id="pepper:113",
        title="t",
        price=80,
        link="",
        source="pepper",
        description="",
        temperature=0,
        image_url="",
        published_at="",
    )
    fetcher.ingest_one(session, dto2, profile={})
    session.commit()
    types = [e.event_type for e in session.query(DealEvent).order_by(DealEvent.id.asc()).all()]
    assert types == ["new_listing", "price_drop"]
    drop_payload = session.query(DealEvent).filter_by(event_type="price_drop").one().payload
    assert drop_payload["old_price"] == 100
    assert drop_payload["new_price"] == 80
