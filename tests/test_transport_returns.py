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


class TestRecordingFromTypedSends:
    """Each typed send_* method records exactly one row on success and zero on failure."""

    def _setup(self, monkeypatch, success: bool):
        """Patch HTTP + capture record_sent_notification calls."""
        from deal_hunter.notifiers.telegram import transport as tr

        resp = _mock_response(200 if success else 500)
        monkeypatch.setattr(tr.time, "sleep", lambda *_a, **_k: None)
        monkeypatch.setattr(tr.requests, "post", lambda *a, **k: resp)

        captured: list[dict] = []

        def _capture(**kw):
            captured.append(kw)

        monkeypatch.setattr(tr, "record_sent_notification", _capture)
        return captured

    def test_send_alert_records_with_deal_type(self, monkeypatch, notifier):
        from deal_hunter.sources.base import Deal

        captured = self._setup(monkeypatch, success=True)
        deal = Deal(
            id="pepper:1",
            title="x",
            price=100,
            link="https://x",
            source="pepper",
            description="",
            temperature=0,
            image_url="",
            published_at="",
        )
        notifier.send_alert(deal, 80, "tier", ["+a"], ["-b"], profile="bikes")
        assert len(captured) == 1
        assert captured[0]["alert_type"] == "deal"
        assert captured[0]["deal_id"] == "pepper:1"
        assert captured[0]["profile"] == "bikes"
        payload = captured[0]["payload"]
        assert payload["title"] == "x"
        assert payload["price"] == 100
        assert payload["score"] == 80

    def test_send_price_drop_alert_records(self, monkeypatch, notifier):
        from deal_hunter.sources.base import Deal

        captured = self._setup(monkeypatch, success=True)
        deal = Deal(
            id="pepper:2",
            title="y",
            price=80,
            link="https://y",
            source="pepper",
            description="",
            temperature=0,
            image_url="",
            published_at="",
        )
        pc = {
            "old_price": 200,
            "new_price": 80,
            "diff_pln": 120,
            "diff_percent": 60.0,
            "is_lowest_ever": True,
        }
        notifier.send_price_drop_alert(deal, pc, profile="bikes")
        assert len(captured) == 1
        assert captured[0]["alert_type"] == "price_drop"
        assert captured[0]["deal_id"] == "pepper:2"
        assert captured[0]["payload"]["is_lowest_ever"] is True

    def test_send_watchlist_alert_records(self, monkeypatch, notifier):
        from deal_hunter.sources.base import Deal

        captured = self._setup(monkeypatch, success=True)
        deal = Deal(
            id="pepper:3",
            title="z",
            price=70,
            link="https://z",
            source="pepper",
            description="",
            temperature=0,
            image_url="",
            published_at="",
        )
        notifier.send_watchlist_alert(deal, target_price=80, current_price=70, profile="bikes")
        assert len(captured) == 1
        assert captured[0]["alert_type"] == "watchlist"
        assert captured[0]["deal_id"] == "pepper:3"
        assert captured[0]["payload"]["target_price"] == 80

    def test_send_digest_records(self, monkeypatch, notifier):
        captured = self._setup(monkeypatch, success=True)
        notifier.send_digest(
            [
                {
                    "id": "p:1",
                    "title": "x",
                    "old_price": 200,
                    "new_price": 100,
                    "diff_pln": 100,
                    "diff_percent": 50.0,
                    "is_lowest_ever": False,
                }
            ]
        )
        assert len(captured) == 1
        assert captured[0]["alert_type"] == "digest"
        assert captured[0]["deal_id"] is None
        assert captured[0]["profile"] is None
        assert captured[0]["payload"]["drop_count"] == 1

    def test_send_summary_records(self, monkeypatch, notifier):
        from deal_hunter.sources.base import Deal

        captured = self._setup(monkeypatch, success=True)
        deals = [
            Deal(
                id=f"pepper:{i}",
                title=f"t{i}",
                price=100 + i,
                link=f"https://x/{i}",
                source="pepper",
                description="",
                temperature=0,
                image_url="",
                published_at="",
            )
            for i in range(3)
        ]
        notifier.send_summary(
            [{"deal": d, "score": 70} for d in deals],
            profile="bikes",
        )
        assert len(captured) == 1
        assert captured[0]["alert_type"] == "summary"
        assert captured[0]["profile"] == "bikes"
        assert captured[0]["payload"]["remaining_count"] == 3

    def test_no_record_on_telegram_failure(self, monkeypatch, notifier):
        from deal_hunter.sources.base import Deal

        captured = self._setup(monkeypatch, success=False)
        deal = Deal(
            id="pepper:1",
            title="x",
            price=100,
            link="",
            source="",
            description="",
            temperature=0,
            image_url="",
            published_at="",
        )
        notifier.send_alert(deal, 0, "", [], [], profile="bikes")
        assert captured == []
