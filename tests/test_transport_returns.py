"""Tests asserting that low-level transport methods return bool (True = success)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from deal_hunter.notifiers.telegram.transport import TelegramNotifier


@pytest.fixture
def notifier():
    return TelegramNotifier(bot_token="test-token", chat_id="42")  # noqa: S106


def _mock_response(status_code: int, json_body: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = "ok"
    resp.json.return_value = json_body or {"ok": True}
    return resp


def test_send_message_returns_true_on_200(notifier):
    with (
        patch("deal_hunter.notifiers.telegram.transport.time.sleep"),
        patch(
            "deal_hunter.notifiers.telegram.transport.requests.post",
            return_value=_mock_response(200),
        ),
    ):
        ok = notifier._send_message("hi")
    assert ok is True


def test_send_message_returns_false_after_failures(notifier):
    with (
        patch("deal_hunter.notifiers.telegram.transport.time.sleep"),
        patch(
            "deal_hunter.notifiers.telegram.transport.requests.post",
            return_value=_mock_response(500),
        ),
    ):
        ok = notifier._send_message("hi")
    assert ok is False


def test_send_text_forwards_send_message_return(notifier):
    with (
        patch("deal_hunter.notifiers.telegram.transport.time.sleep"),
        patch(
            "deal_hunter.notifiers.telegram.transport.requests.post",
            return_value=_mock_response(200),
        ),
    ):
        assert notifier.send_text("hi") is True

    with (
        patch("deal_hunter.notifiers.telegram.transport.time.sleep"),
        patch(
            "deal_hunter.notifiers.telegram.transport.requests.post",
            return_value=_mock_response(500),
        ),
    ):
        assert notifier.send_text("hi") is False


def test_send_photo_returns_true_on_200(notifier, tmp_path):
    fake = tmp_path / "x.png"
    fake.write_bytes(b"x")
    with (
        patch("deal_hunter.notifiers.telegram.transport.time.sleep"),
        patch(
            "deal_hunter.notifiers.telegram.transport.requests.post",
            return_value=_mock_response(200),
        ),
    ):
        assert notifier.send_photo(str(fake)) is True


def test_send_photo_returns_false_after_failures(notifier, tmp_path):
    fake = tmp_path / "x.png"
    fake.write_bytes(b"x")
    with (
        patch("deal_hunter.notifiers.telegram.transport.time.sleep"),
        patch(
            "deal_hunter.notifiers.telegram.transport.requests.post",
            return_value=_mock_response(500),
        ),
    ):
        assert notifier.send_photo(str(fake)) is False
