"""Tests for JSON state migration script."""

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.models import Base, SeenDeal
from storage.models import PricePoint as PriceHistory


@pytest.fixture
def engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s


def test_migrate_new_format(tmp_path, session, monkeypatch):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    state_file = state_dir / "bikes_state.json"
    state_file.write_text(
        json.dumps(
            {
                "seen": {"pepper:1": "2026-04-13T10:00:00", "pepper:2": "2026-04-13T11:00:00"},
                "prices": {"pepper:1": [{"price": 5000, "ts": "2026-04-10T10:00:00"}]},
            }
        )
    )

    import scripts.migrate_json_state as mig

    monkeypatch.setattr(mig, "STATE_DIR", state_dir)

    counts = mig.migrate_file(state_file, session)
    session.commit()

    assert counts["seen"] == 2
    assert counts["prices"] == 1

    seen = session.query(SeenDeal).all()
    assert len(seen) == 2

    prices = session.query(PriceHistory).filter_by(offer_id="pepper:1").all()
    assert len(prices) == 1


def test_migrate_idempotent(tmp_path, session, monkeypatch):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    state_file = state_dir / "bikes_state.json"
    state_file.write_text(
        json.dumps(
            {
                "seen": {"pepper:1": "2026-04-13T10:00:00"},
                "prices": {},
            }
        )
    )

    import scripts.migrate_json_state as mig

    monkeypatch.setattr(mig, "STATE_DIR", state_dir)

    # Run twice
    mig.migrate_file(state_file, session)
    session.commit()
    counts2 = mig.migrate_file(state_file, session)
    assert counts2["skipped"] == 1
