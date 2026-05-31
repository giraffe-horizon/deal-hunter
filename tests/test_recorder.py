"""Tests for record_sent_notification — fire-and-forget recorder."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from deal_hunter.notifiers.telegram.recorder import record_sent_notification
from deal_hunter.storage.models import Base
from deal_hunter.storage.repositories import SentNotificationRepository


@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    return eng


def test_record_writes_row(engine):
    @contextmanager
    def _factory():
        with Session(engine) as s:
            yield s
            s.commit()

    with patch("deal_hunter.notifiers.telegram.recorder.get_session", _factory):
        record_sent_notification(
            alert_type="price_drop",
            payload={"title": "x", "old_price": 200, "new_price": 100},
            deal_id="pepper:1",
            profile="bikes",
        )

    with Session(engine) as s:
        rows = SentNotificationRepository(s).list_recent(limit=10)
    assert len(rows) == 1
    assert rows[0]["alert_type"] == "price_drop"
    assert rows[0]["deal_id"] == "pepper:1"
    assert rows[0]["profile"] == "bikes"
    assert rows[0]["payload"]["title"] == "x"


def test_record_swallows_db_errors(caplog):
    """A DB blip must not propagate — log WARNING and move on."""

    @contextmanager
    def _broken_factory():
        raise OperationalError("boom", {}, Exception("boom"))
        yield  # unreachable

    with (
        patch("deal_hunter.notifiers.telegram.recorder.get_session", _broken_factory),
        caplog.at_level(logging.WARNING),
    ):
        record_sent_notification(
            alert_type="deal",
            payload={"x": 1},
        )

    assert any(
        "sent_notifications insert failed" in rec.message
        for rec in caplog.records
        if rec.levelno == logging.WARNING
    )


def test_record_swallows_repository_errors(caplog, engine):
    """If the repository raises mid-insert, recording still swallows."""

    @contextmanager
    def _factory():
        with Session(engine) as s:
            yield s
            s.commit()

    with (
        patch("deal_hunter.notifiers.telegram.recorder.get_session", _factory),
        patch(
            "deal_hunter.notifiers.telegram.recorder.SentNotificationRepository.record",
            side_effect=OperationalError("boom", {}, Exception("boom")),
        ),
        caplog.at_level(logging.WARNING),
    ):
        record_sent_notification(alert_type="deal", payload={})

    assert any("sent_notifications insert failed" in rec.message for rec in caplog.records)
