"""Tests for quiet hours alert queuing."""

import json
from pathlib import Path

import pytest

from storage.sqlite import SQLiteStorage


@pytest.fixture
def db(tmp_path):
    """Fresh SQLite database for each test."""
    return SQLiteStorage(tmp_path / "test.db")


class TestAlertQueue:
    """Tests for alert_queue SQLite table and methods."""

    def test_queue_alert_stores_entry(self, db):
        payload = json.dumps({"deal_id": "pepper:123", "title": "Test Deal", "score": 85})
        db.queue_alert("bikes", "deal", payload)
        pending = db.get_pending_alerts()
        assert len(pending) == 1
        assert pending[0]["profile"] == "bikes"
        assert pending[0]["alert_type"] == "deal"
        assert json.loads(pending[0]["payload"])["deal_id"] == "pepper:123"

    def test_queue_multiple_alerts(self, db):
        db.queue_alert("bikes", "deal", json.dumps({"id": "1"}))
        db.queue_alert("bikes", "price_drop", json.dumps({"id": "2"}))
        db.queue_alert("nas_hdd", "deal", json.dumps({"id": "3"}))
        pending = db.get_pending_alerts()
        assert len(pending) == 3

    def test_get_pending_alerts_filters_by_profile(self, db):
        db.queue_alert("bikes", "deal", json.dumps({"id": "1"}))
        db.queue_alert("nas_hdd", "deal", json.dumps({"id": "2"}))
        pending = db.get_pending_alerts(profile="bikes")
        assert len(pending) == 1
        assert pending[0]["profile"] == "bikes"

    def test_get_pending_alerts_excludes_sent(self, db):
        db.queue_alert("bikes", "deal", json.dumps({"id": "1"}))
        db.queue_alert("bikes", "deal", json.dumps({"id": "2"}))
        pending = db.get_pending_alerts()
        db.mark_alerts_sent([pending[0]["id"]])
        remaining = db.get_pending_alerts()
        assert len(remaining) == 1
        assert remaining[0]["id"] == pending[1]["id"]

    def test_mark_alerts_sent_updates_sent_at(self, db):
        db.queue_alert("bikes", "deal", json.dumps({"id": "1"}))
        pending = db.get_pending_alerts()
        db.mark_alerts_sent([pending[0]["id"]])
        assert db.get_pending_alerts() == []

    def test_mark_alerts_sent_empty_list(self, db):
        db.mark_alerts_sent([])

    def test_queue_alert_sets_created_at(self, db):
        db.queue_alert("bikes", "deal", json.dumps({"id": "1"}))
        pending = db.get_pending_alerts()
        assert pending[0]["created_at"] is not None

    def test_get_pending_alerts_ordered_by_created_at(self, db):
        db.queue_alert("bikes", "deal", json.dumps({"id": "first"}))
        db.queue_alert("bikes", "deal", json.dumps({"id": "second"}))
        pending = db.get_pending_alerts()
        assert json.loads(pending[0]["payload"])["id"] == "first"
        assert json.loads(pending[1]["payload"])["id"] == "second"
