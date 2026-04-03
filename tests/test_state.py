"""Tests for state management — load_state, save_state, TTL cleanup."""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import deal_hunter


class TestLoadState:
    def test_missing_file_returns_empty(self, tmp_path):
        with patch.object(deal_hunter, "STATE_DIR", tmp_path):
            state = deal_hunter.load_state("nonexistent")
        assert state == {"seen": {}, "prices": {}}

    def test_valid_state_loaded(self, tmp_path):
        state_file = tmp_path / "test_state.json"
        data = {
            "seen": {"pepper:1": datetime.now().isoformat()},
            "prices": {},
        }
        state_file.write_text(json.dumps(data))
        with patch.object(deal_hunter, "STATE_DIR", tmp_path):
            state = deal_hunter.load_state("test")
        assert "pepper:1" in state["seen"]

    def test_ttl_cleanup(self, tmp_path):
        old_ts = (datetime.now() - timedelta(days=30)).isoformat()
        fresh_ts = datetime.now().isoformat()
        state_file = tmp_path / "test_state.json"
        data = {
            "seen": {"old:1": old_ts, "fresh:1": fresh_ts},
            "prices": {},
        }
        state_file.write_text(json.dumps(data))
        with patch.object(deal_hunter, "STATE_DIR", tmp_path):
            state = deal_hunter.load_state("test")
        assert "old:1" not in state["seen"]
        assert "fresh:1" in state["seen"]

    def test_corrupted_file_returns_empty(self, tmp_path):
        state_file = tmp_path / "test_state.json"
        state_file.write_text("not valid json {{{")
        with patch.object(deal_hunter, "STATE_DIR", tmp_path):
            state = deal_hunter.load_state("test")
        assert state == {"seen": {}, "prices": {}}

    def test_old_flat_format_migrated(self, tmp_path):
        """Old format was a flat dict of id: timestamp."""
        fresh_ts = datetime.now().isoformat()
        state_file = tmp_path / "test_state.json"
        data = {"pepper:1": fresh_ts, "ceneo:2": fresh_ts}
        state_file.write_text(json.dumps(data))
        with patch.object(deal_hunter, "STATE_DIR", tmp_path):
            state = deal_hunter.load_state("test")
        assert "seen" in state
        assert "prices" in state
        assert "pepper:1" in state["seen"]

    def test_old_list_format_migrated(self, tmp_path):
        """Very old format was a plain list."""
        state_file = tmp_path / "test_state.json"
        state_file.write_text(json.dumps(["pepper:1", "ceneo:2"]))
        with patch.object(deal_hunter, "STATE_DIR", tmp_path):
            state = deal_hunter.load_state("test")
        assert "seen" in state
        assert "pepper:1" in state["seen"]


class TestSaveState:
    def test_save_and_reload(self, tmp_path):
        data = {
            "seen": {"pepper:1": datetime.now().isoformat()},
            "prices": {"test|pepper": [{"price": 100, "ts": datetime.now().isoformat()}]},
        }
        with patch.object(deal_hunter, "STATE_DIR", tmp_path):
            deal_hunter.save_state("test", data)
            loaded = deal_hunter.load_state("test")
        assert loaded["seen"] == data["seen"]
        assert loaded["prices"] == data["prices"]
