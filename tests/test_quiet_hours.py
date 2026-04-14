"""Tests for quiet hours alert queuing."""

import json
from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from deal_hunter.storage.models import Base
from deal_hunter.storage.repositories import AlertQueueRepository
from deal_hunter.utils.validation import validate_profile


@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s


@pytest.fixture
def alert_repo(session):
    return AlertQueueRepository(session)


class TestAlertQueue:
    """Tests for alert_queue table and methods."""

    def test_queue_alert_stores_entry(self, session, alert_repo):
        payload = json.dumps({"deal_id": "pepper:123", "title": "Test Deal", "score": 85})
        alert_repo.queue("bikes", "deal", payload)
        session.flush()
        pending = alert_repo.get_pending()
        assert len(pending) == 1
        assert pending[0]["profile"] == "bikes"
        assert pending[0]["alert_type"] == "deal"
        assert json.loads(pending[0]["payload"])["deal_id"] == "pepper:123"

    def test_queue_multiple_alerts(self, session, alert_repo):
        alert_repo.queue("bikes", "deal", json.dumps({"id": "1"}))
        alert_repo.queue("bikes", "price_drop", json.dumps({"id": "2"}))
        alert_repo.queue("nas_hdd", "deal", json.dumps({"id": "3"}))
        session.flush()
        pending = alert_repo.get_pending()
        assert len(pending) == 3

    def test_get_pending_alerts_filters_by_profile(self, session, alert_repo):
        alert_repo.queue("bikes", "deal", json.dumps({"id": "1"}))
        alert_repo.queue("nas_hdd", "deal", json.dumps({"id": "2"}))
        session.flush()
        pending = alert_repo.get_pending(profile="bikes")
        assert len(pending) == 1
        assert pending[0]["profile"] == "bikes"

    def test_get_pending_alerts_excludes_sent(self, session, alert_repo):
        alert_repo.queue("bikes", "deal", json.dumps({"id": "1"}))
        alert_repo.queue("bikes", "deal", json.dumps({"id": "2"}))
        session.flush()
        pending = alert_repo.get_pending()
        alert_repo.mark_sent([pending[0]["id"]])
        session.flush()
        remaining = alert_repo.get_pending()
        assert len(remaining) == 1
        assert remaining[0]["id"] == pending[1]["id"]

    def test_mark_alerts_sent_updates_sent_at(self, session, alert_repo):
        alert_repo.queue("bikes", "deal", json.dumps({"id": "1"}))
        session.flush()
        pending = alert_repo.get_pending()
        alert_repo.mark_sent([pending[0]["id"]])
        session.flush()
        assert alert_repo.get_pending() == []

    def test_mark_alerts_sent_empty_list(self, alert_repo):
        alert_repo.mark_sent([])

    def test_queue_alert_sets_created_at(self, session, alert_repo):
        alert_repo.queue("bikes", "deal", json.dumps({"id": "1"}))
        session.flush()
        pending = alert_repo.get_pending()
        assert pending[0]["created_at"] is not None

    def test_get_pending_alerts_ordered_by_created_at(self, session, alert_repo):
        alert_repo.queue("bikes", "deal", json.dumps({"id": "first"}))
        alert_repo.queue("bikes", "deal", json.dumps({"id": "second"}))
        session.flush()
        pending = alert_repo.get_pending()
        assert json.loads(pending[0]["payload"])["id"] == "first"
        assert json.loads(pending[1]["payload"])["id"] == "second"


class TestIsQuietHours:
    """Tests for is_quiet_hours() time checking logic."""

    def test_inside_quiet_hours_evening(self):
        from deal_hunter.services.alerter import is_quiet_hours

        profile = {"quiet_hours": {"start": "22:00", "end": "07:00"}}
        with patch("deal_hunter.services.alerter.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 6, 23, 30)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert is_quiet_hours(profile) is True

    def test_inside_quiet_hours_early_morning(self):
        from deal_hunter.services.alerter import is_quiet_hours

        profile = {"quiet_hours": {"start": "22:00", "end": "07:00"}}
        with patch("deal_hunter.services.alerter.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 6, 5, 0)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert is_quiet_hours(profile) is True

    def test_outside_quiet_hours_afternoon(self):
        from deal_hunter.services.alerter import is_quiet_hours

        profile = {"quiet_hours": {"start": "22:00", "end": "07:00"}}
        with patch("deal_hunter.services.alerter.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 6, 14, 0)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert is_quiet_hours(profile) is False

    def test_no_quiet_hours_config(self):
        from deal_hunter.services.alerter import is_quiet_hours

        profile = {}
        assert is_quiet_hours(profile) is False

    def test_quiet_hours_from_env(self):
        from deal_hunter.services.alerter import is_quiet_hours

        profile = {}
        with patch("deal_hunter.services.alerter.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 6, 23, 30)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            with patch.dict(
                "os.environ", {"QUIET_HOURS_START": "22:00", "QUIET_HOURS_END": "07:00"}
            ):
                assert is_quiet_hours(profile) is True

    def test_profile_overrides_env(self):
        from deal_hunter.services.alerter import is_quiet_hours

        profile = {"quiet_hours": {"start": "23:00", "end": "06:00"}}
        with patch("deal_hunter.services.alerter.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 6, 22, 30)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            with patch.dict(
                "os.environ", {"QUIET_HOURS_START": "22:00", "QUIET_HOURS_END": "07:00"}
            ):
                assert is_quiet_hours(profile) is False

    def test_same_day_quiet_hours(self):
        from deal_hunter.services.alerter import is_quiet_hours

        profile = {"quiet_hours": {"start": "13:00", "end": "15:00"}}
        with patch("deal_hunter.services.alerter.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 6, 14, 0)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert is_quiet_hours(profile) is True

    def test_at_exact_start_time_is_quiet(self):
        from deal_hunter.services.alerter import is_quiet_hours

        profile = {"quiet_hours": {"start": "22:00", "end": "07:00"}}
        with patch("deal_hunter.services.alerter.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 6, 22, 0)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert is_quiet_hours(profile) is True

    def test_at_exact_end_time_is_not_quiet(self):
        from deal_hunter.services.alerter import is_quiet_hours

        profile = {"quiet_hours": {"start": "22:00", "end": "07:00"}}
        with patch("deal_hunter.services.alerter.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 6, 7, 0)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert is_quiet_hours(profile) is False


class TestQuietHoursIntegration:
    """Tests for quiet hours integration with alert flow."""

    def test_flush_pending_alerts_sends_and_marks(self, session, alert_repo):
        """flush_pending_alerts should send queued alerts and mark them sent."""
        alert_repo.queue(
            "bikes",
            "deal",
            json.dumps(
                {
                    "deal_id": "pepper:123",
                    "title": "Test Deal",
                    "price": 5000,
                    "link": "https://example.com",
                    "score": 85,
                    "plus": ["keyword1"],
                    "minus": [],
                }
            ),
        )
        alert_repo.queue(
            "bikes",
            "price_drop",
            json.dumps(
                {
                    "deal_id": "pepper:456",
                    "title": "Drop Deal",
                    "old_price": 10000,
                    "new_price": 8000,
                    "diff_pln": 2000,
                    "diff_percent": 20.0,
                    "link": "https://example.com/2",
                }
            ),
        )
        session.flush()

        pending = alert_repo.get_pending()
        assert len(pending) == 2

        # Mark all as sent (simulating flush)
        alert_repo.mark_sent([p["id"] for p in pending])
        session.flush()
        assert alert_repo.get_pending() == []

    def test_flush_respects_max_alerts(self, session, alert_repo):
        """Only first 5 alerts should be sent, rest stay queued."""
        for i in range(8):
            alert_repo.queue("bikes", "deal", json.dumps({"id": str(i)}))
        session.flush()

        pending = alert_repo.get_pending()
        assert len(pending) == 8

        # Flush only first 5
        to_send = pending[:5]
        alert_repo.mark_sent([p["id"] for p in to_send])
        session.flush()
        remaining = alert_repo.get_pending()
        assert len(remaining) == 3


class TestQuietHoursValidation:
    """Tests for quiet_hours config validation."""

    VALID_PROFILE = {
        "name": "test",
        "sources": {"pepper": {}},
        "budget": {"min": 100, "max": 10000},
        "score_threshold": 50,
        "telegram": {"topic_id": 1},
    }

    def test_valid_quiet_hours(self):
        profile = {**self.VALID_PROFILE, "quiet_hours": {"start": "22:00", "end": "07:00"}}
        errors = validate_profile(profile)
        assert not errors

    def test_invalid_quiet_hours_not_dict(self):
        profile = {**self.VALID_PROFILE, "quiet_hours": "22:00-07:00"}
        errors = validate_profile(profile)
        assert any("quiet_hours" in e and "dict" in e for e in errors)

    def test_invalid_quiet_hours_missing_start(self):
        profile = {**self.VALID_PROFILE, "quiet_hours": {"end": "07:00"}}
        errors = validate_profile(profile)
        assert any("start" in e for e in errors)

    def test_invalid_quiet_hours_missing_end(self):
        profile = {**self.VALID_PROFILE, "quiet_hours": {"start": "22:00"}}
        errors = validate_profile(profile)
        assert any("end" in e for e in errors)

    def test_invalid_quiet_hours_bad_format(self):
        profile = {**self.VALID_PROFILE, "quiet_hours": {"start": "10pm", "end": "7am"}}
        errors = validate_profile(profile)
        assert any("HH:MM" in e for e in errors)

    def test_no_quiet_hours_is_valid(self):
        errors = validate_profile(self.VALID_PROFILE)
        assert not errors
