"""Tests for SentNotificationRepository."""

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from deal_hunter.storage.models import Base
from deal_hunter.storage.repositories import SentNotificationRepository


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
def repo(session):
    return SentNotificationRepository(session)


class TestRecord:
    def test_record_writes_row(self, session, repo):
        repo.record(
            alert_type="price_drop",
            payload_json='{"x": 1}',
            deal_id="pepper:1",
            profile="bikes",
            sent_at="2026-05-12T10:00:00",
        )
        session.flush()
        rows = repo.list_recent(limit=10)
        assert len(rows) == 1
        assert rows[0]["alert_type"] == "price_drop"
        assert rows[0]["deal_id"] == "pepper:1"
        assert rows[0]["profile"] == "bikes"
        assert rows[0]["payload"] == {"x": 1}  # decoded
        assert rows[0]["sent_at"] == "2026-05-12T10:00:00"

    def test_record_defaults_sent_at_to_now(self, session, repo):
        before = datetime.now().isoformat()
        repo.record(alert_type="deal", payload_json="{}")
        session.flush()
        rows = repo.list_recent(limit=1)
        assert rows[0]["sent_at"] >= before

    def test_record_with_nullable_fields(self, session, repo):
        repo.record(alert_type="digest", payload_json='{"drop_count": 3}')
        session.flush()
        rows = repo.list_recent(limit=1)
        assert rows[0]["deal_id"] is None
        assert rows[0]["profile"] is None


class TestLastSentAt:
    def test_returns_none_when_no_rows(self, repo):
        assert repo.last_sent_at("pepper:1", "price_drop") is None

    def test_returns_max_for_pair(self, session, repo):
        repo.record(
            alert_type="price_drop",
            payload_json="{}",
            deal_id="pepper:1",
            sent_at="2026-05-10T10:00:00",
        )
        repo.record(
            alert_type="price_drop",
            payload_json="{}",
            deal_id="pepper:1",
            sent_at="2026-05-12T10:00:00",
        )
        session.flush()
        assert repo.last_sent_at("pepper:1", "price_drop") == "2026-05-12T10:00:00"

    def test_ignores_other_deal_ids(self, session, repo):
        repo.record(
            alert_type="price_drop",
            payload_json="{}",
            deal_id="pepper:other",
            sent_at="2026-05-12T10:00:00",
        )
        session.flush()
        assert repo.last_sent_at("pepper:1", "price_drop") is None

    def test_ignores_other_alert_types(self, session, repo):
        repo.record(
            alert_type="deal",
            payload_json="{}",
            deal_id="pepper:1",
            sent_at="2026-05-12T10:00:00",
        )
        session.flush()
        assert repo.last_sent_at("pepper:1", "price_drop") is None


class TestListRecent:
    def test_orders_by_sent_at_desc(self, session, repo):
        repo.record(alert_type="a", payload_json="{}", sent_at="2026-05-10T10:00:00")
        repo.record(alert_type="b", payload_json="{}", sent_at="2026-05-12T10:00:00")
        repo.record(alert_type="c", payload_json="{}", sent_at="2026-05-11T10:00:00")
        session.flush()
        rows = repo.list_recent(limit=10)
        assert [r["alert_type"] for r in rows] == ["b", "c", "a"]

    def test_filter_by_alert_type(self, session, repo):
        repo.record(alert_type="deal", payload_json="{}")
        repo.record(alert_type="price_drop", payload_json="{}")
        repo.record(alert_type="deal", payload_json="{}")
        session.flush()
        rows = repo.list_recent(alert_type="deal", limit=10)
        assert len(rows) == 2
        assert all(r["alert_type"] == "deal" for r in rows)

    def test_filter_by_profile(self, session, repo):
        repo.record(alert_type="deal", payload_json="{}", profile="bikes")
        repo.record(alert_type="deal", payload_json="{}", profile="hifi")
        session.flush()
        rows = repo.list_recent(profile="bikes", limit=10)
        assert len(rows) == 1
        assert rows[0]["profile"] == "bikes"

    def test_filter_by_since(self, session, repo):
        repo.record(alert_type="a", payload_json="{}", sent_at="2026-05-10T00:00:00")
        repo.record(alert_type="b", payload_json="{}", sent_at="2026-05-12T00:00:00")
        session.flush()
        rows = repo.list_recent(since="2026-05-11T00:00:00", limit=10)
        assert [r["alert_type"] for r in rows] == ["b"]

    def test_limit_and_offset(self, session, repo):
        for i in range(5):
            repo.record(
                alert_type="a",
                payload_json="{}",
                sent_at=f"2026-05-{10 + i:02d}T00:00:00",
            )
        session.flush()
        page1 = repo.list_recent(limit=2, offset=0)
        page2 = repo.list_recent(limit=2, offset=2)
        assert len(page1) == 2
        assert len(page2) == 2
        # Newest first, no overlap
        assert page1[0]["sent_at"] > page2[0]["sent_at"]


class TestCount:
    def test_count_matches_list_recent(self, session, repo):
        for _ in range(7):
            repo.record(alert_type="deal", payload_json="{}", profile="bikes")
        repo.record(alert_type="price_drop", payload_json="{}", profile="hifi")
        session.flush()

        assert repo.count() == 8
        assert repo.count(alert_type="deal") == 7
        assert repo.count(profile="bikes") == 7
        assert repo.count(alert_type="price_drop", profile="hifi") == 1


class TestDistinctProfiles:
    def test_empty_table_returns_empty_list(self, repo):
        assert repo.distinct_profiles() == []

    def test_returns_only_non_null_profiles(self, session, repo):
        repo.record(alert_type="deal", payload_json="{}", profile="bikes")
        repo.record(alert_type="deal", payload_json="{}", profile="hifi")
        repo.record(alert_type="digest", payload_json="{}")  # NULL profile
        session.flush()
        result = repo.distinct_profiles()
        assert set(result) == {"bikes", "hifi"}

    def test_deduplicates_repeated_profiles(self, session, repo):
        for _ in range(5):
            repo.record(alert_type="deal", payload_json="{}", profile="bikes")
        session.flush()
        assert repo.distinct_profiles() == ["bikes"]

    def test_result_is_sorted(self, session, repo):
        repo.record(alert_type="deal", payload_json="{}", profile="z")
        repo.record(alert_type="deal", payload_json="{}", profile="a")
        repo.record(alert_type="deal", payload_json="{}", profile="m")
        session.flush()
        assert repo.distinct_profiles() == ["a", "m", "z"]
