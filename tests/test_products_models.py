"""Schema sanity tests for Product/ProductAlias ORM models."""

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from deal_hunter.storage.models import Base, Product, ProductAlias


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_product_roundtrip(session: Session) -> None:
    now = datetime.now().isoformat()
    p = Product(
        id="prod-1",
        canonical_title="Rondo Ruut",
        brand="Rondo",
        model="Ruut",
        category="bikes",
        attributes={"size": "M", "year": 2025},
        review_status="auto",
        created_at=now,
        updated_at=now,
    )
    session.add(p)
    session.commit()
    loaded = session.get(Product, "prod-1")
    assert loaded is not None
    assert loaded.attributes == {"size": "M", "year": 2025}
    assert loaded.archived == 0


def test_product_alias_fk(session: Session) -> None:
    now = datetime.now().isoformat()
    session.add(
        Product(
            id="p1",
            canonical_title="t",
            category="bikes",
            attributes={},
            review_status="auto",
            created_at=now,
            updated_at=now,
        )
    )
    session.add(
        ProductAlias(
            product_id="p1",
            identifier_type="ean",
            identifier_value="5900000000001",
            confidence=1.0,
            created_by="auto",
            created_at=now,
        )
    )
    session.commit()
    aliases = session.query(ProductAlias).filter_by(product_id="p1").all()
    assert len(aliases) == 1
    assert aliases[0].identifier_type == "ean"


def test_match_review_roundtrip(session: Session) -> None:
    from deal_hunter.storage.models import MatchReview, Offer

    now = datetime.now().isoformat()
    session.add(
        Offer(
            id="pepper:50",
            raw_title="t",
            source="pepper",
            first_seen_at=now,
            last_seen_at=now,
        )
    )
    session.commit()
    session.add(
        MatchReview(
            offer_id="pepper:50",
            status="pending",
            priority=42,
            created_at=now,
        )
    )
    session.commit()
    row = session.query(MatchReview).one()
    assert row.status == "pending"
    assert row.priority == 42


def test_match_decision_roundtrip(session: Session) -> None:
    from deal_hunter.storage.models import MatchDecision

    now = datetime.now().isoformat()
    session.add(
        MatchDecision(
            decision_type="auto_strong",
            actor="auto",
            confidence=0.95,
            signals={"brand": "matched"},
            created_at=now,
        )
    )
    session.commit()
    row = session.query(MatchDecision).one()
    assert row.decision_type == "auto_strong"
    assert row.signals == {"brand": "matched"}


def test_fx_rate_roundtrip(session: Session) -> None:
    from deal_hunter.storage.models import FxRate

    now = datetime.now().isoformat()
    session.add(FxRate(currency="EUR", rate_to_pln=4.30, fetched_at=now, table_no="A/076/2026"))
    session.commit()
    row = session.query(FxRate).one()
    assert row.rate_to_pln == 4.30
