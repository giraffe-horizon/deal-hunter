"""Tests for Telegram feedback bot — SQLite additions, callback parsing, inline keyboard."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from notifiers.telegram import build_deal_keyboard
from sources.base import Deal
from storage.sqlite import SQLiteStorage

# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def db(tmp_path):
    storage = SQLiteStorage(tmp_path / "test.db")
    yield storage
    storage.close()


@pytest.fixture
def deal():
    return Deal(
        id="pepper:77777",
        title="Test Feedback Deal",
        price=5000,
        link="https://example.com/deal/77777",
        source="pepper",
        description="A test deal for feedback",
        temperature=50,
        image_url="",
        published_at="2026-04-01T10:00:00",
    )


@pytest.fixture
def deal2():
    return Deal(
        id="ceneo:66666",
        title="Another Test Deal",
        price=3000,
        link="https://ceneo.pl/66666",
        source="ceneo",
        description="Another deal",
        temperature=0,
        image_url="",
        published_at="2026-04-02T12:00:00",
    )


# ── SQLite additions ─────────────────────────────────────────────────


class TestUpdateDealStatus:
    def test_update_existing_deal(self, db, deal):
        db.upsert_deal(deal, "test", 100)
        result = db.update_deal_status("pepper:77777", "watching")
        assert result is True
        row = db.get_deal("pepper:77777")
        assert row["status"] == "watching"

    def test_update_nonexistent_deal(self, db):
        result = db.update_deal_status("nonexistent:000", "watching")
        assert result is False

    def test_update_to_rejected(self, db, deal):
        db.upsert_deal(deal, "test", 100)
        db.update_deal_status("pepper:77777", "rejected")
        row = db.get_deal("pepper:77777")
        assert row["status"] == "rejected"


class TestGetDealsByStatus:
    def test_filter_watching(self, db, deal, deal2):
        db.upsert_deal(deal, "test", 100)
        db.upsert_deal(deal2, "test", 80)
        db.update_deal_status("pepper:77777", "watching")

        watching = db.get_deals_by_status("watching")
        assert len(watching) == 1
        assert watching[0]["id"] == "pepper:77777"

    def test_empty_result(self, db, deal):
        db.upsert_deal(deal, "test", 100)
        assert db.get_deals_by_status("watching") == []

    def test_limit(self, db):
        for i in range(5):
            d = Deal(
                id=f"test:{i}",
                title=f"Deal {i}",
                price=1000,
                link="https://example.com",
                source="test",
                description="",
                temperature=0,
                image_url="",
                published_at="2026-04-01T10:00:00",
            )
            db.upsert_deal(d, "test", 50)
            db.update_deal_status(f"test:{i}", "watching")

        result = db.get_deals_by_status("watching", limit=3)
        assert len(result) == 3

    def test_ordered_by_last_seen_desc(self, db, deal, deal2):
        db.upsert_deal(deal, "test", 100)
        db.upsert_deal(deal2, "test", 80)
        db.update_deal_status("pepper:77777", "watching")
        db.update_deal_status("ceneo:66666", "watching")

        result = db.get_deals_by_status("watching")
        assert len(result) == 2
        # deal2 was upserted later, so it should be first
        assert result[0]["id"] == "ceneo:66666"


class TestGetFeedbackStats:
    def test_empty_stats(self, db):
        assert db.get_feedback_stats() == {}

    def test_counts_per_action(self, db, deal):
        db.upsert_deal(deal, "test", 100)
        db.record_feedback("pepper:77777", "watch")
        db.record_feedback("pepper:77777", "watch")
        db.record_feedback("pepper:77777", "skip")

        stats = db.get_feedback_stats()
        assert stats["watch"] == 2
        assert stats["skip"] == 1

    def test_multiple_deals(self, db, deal, deal2):
        db.upsert_deal(deal, "test", 100)
        db.upsert_deal(deal2, "test", 80)
        db.record_feedback("pepper:77777", "watch")
        db.record_feedback("ceneo:66666", "skip")

        stats = db.get_feedback_stats()
        assert stats["watch"] == 1
        assert stats["skip"] == 1


# ── Inline keyboard ─────────────────────────────────────────────────


class TestInlineKeyboard:
    def test_keyboard_structure(self):
        kb = build_deal_keyboard("https://example.com/deal", "pepper:123")
        assert "inline_keyboard" in kb
        buttons = kb["inline_keyboard"][0]
        assert len(buttons) == 3

    def test_url_button(self):
        kb = build_deal_keyboard("https://example.com/deal", "pepper:123")
        url_btn = kb["inline_keyboard"][0][0]
        assert url_btn["url"] == "https://example.com/deal"
        assert "Otwórz" in url_btn["text"]

    def test_watch_button(self):
        kb = build_deal_keyboard("https://example.com/deal", "pepper:123")
        watch_btn = kb["inline_keyboard"][0][1]
        assert watch_btn["callback_data"] == "watch:pepper:123"
        assert "Obserwuj" in watch_btn["text"]

    def test_skip_button(self):
        kb = build_deal_keyboard("https://example.com/deal", "pepper:123")
        skip_btn = kb["inline_keyboard"][0][2]
        assert skip_btn["callback_data"] == "skip:pepper:123"
        assert "Skip" in skip_btn["text"]


# ── Callback parsing ────────────────────────────────────────────────


class TestCallbackParsing:
    def test_parse_watch_callback(self):
        data = "watch:pepper:12345"
        action, deal_id = data.split(":", 1)
        assert action == "watch"
        assert deal_id == "pepper:12345"

    def test_parse_skip_callback(self):
        data = "skip:ceneo:99999"
        action, deal_id = data.split(":", 1)
        assert action == "skip"
        assert deal_id == "ceneo:99999"

    def test_parse_unknown_action(self):
        data = "unknown:pepper:123"
        action, deal_id = data.split(":", 1)
        assert action == "unknown"
        assert action not in ("watch", "skip")


# ── Bot command handlers (mocked) ───────────────────────────────────


class TestBotHandlers:
    @pytest.mark.asyncio
    async def test_handle_callback_watch(self, db, deal, tmp_path):
        from feedback_bot import handle_callback

        db.upsert_deal(deal, "test", 100)

        query = AsyncMock()
        query.data = "watch:pepper:77777"
        update = MagicMock()
        update.callback_query = query
        context = MagicMock()

        with patch("feedback_bot.get_storage", return_value=db):
            with patch.object(db, "close"):  # prevent closing our test db
                await handle_callback(update, context)

        query.answer.assert_called_once_with("\u2b50 Dodano do obserwowanych")
        assert db.get_deal("pepper:77777")["status"] == "watching"

    @pytest.mark.asyncio
    async def test_handle_callback_skip(self, db, deal, tmp_path):
        from feedback_bot import handle_callback

        db.upsert_deal(deal, "test", 100)

        query = AsyncMock()
        query.data = "skip:pepper:77777"
        update = MagicMock()
        update.callback_query = query
        context = MagicMock()

        with patch("feedback_bot.get_storage", return_value=db):
            with patch.object(db, "close"):
                await handle_callback(update, context)

        query.answer.assert_called_once_with("\U0001f44e Pominięto")
        assert db.get_deal("pepper:77777")["status"] == "rejected"

    @pytest.mark.asyncio
    async def test_handle_callback_unknown_deal(self, db):
        from feedback_bot import handle_callback

        query = AsyncMock()
        query.data = "watch:nonexistent:000"
        update = MagicMock()
        update.callback_query = query
        context = MagicMock()

        with patch("feedback_bot.get_storage", return_value=db):
            with patch.object(db, "close"):
                await handle_callback(update, context)

        query.answer.assert_called_once_with("Nie znaleziono oferty w bazie")

    @pytest.mark.asyncio
    async def test_cmd_status(self, db, deal):
        from feedback_bot import cmd_status

        db.upsert_deal(deal, "test", 100)
        db.record_feedback("pepper:77777", "watch")

        message = AsyncMock()
        update = MagicMock()
        update.message = message
        context = MagicMock()

        with patch("feedback_bot.get_storage", return_value=db):
            with patch.object(db, "close"):
                await cmd_status(update, context)

        message.reply_text.assert_called_once()
        text = message.reply_text.call_args[0][0]
        assert "Status bazy ofert" in text

    @pytest.mark.asyncio
    async def test_cmd_watchlist_empty(self, db):
        from feedback_bot import cmd_watchlist

        message = AsyncMock()
        update = MagicMock()
        update.message = message
        context = MagicMock()

        with patch("feedback_bot.get_storage", return_value=db):
            with patch.object(db, "close"):
                await cmd_watchlist(update, context)

        message.reply_text.assert_called_once_with("Brak obserwowanych ofert.")

    @pytest.mark.asyncio
    async def test_cmd_watchlist_with_deals(self, db, deal):
        from feedback_bot import cmd_watchlist

        db.upsert_deal(deal, "test", 100)
        db.update_deal_status("pepper:77777", "watching")

        message = AsyncMock()
        update = MagicMock()
        update.message = message
        context = MagicMock()

        with patch("feedback_bot.get_storage", return_value=db):
            with patch.object(db, "close"):
                await cmd_watchlist(update, context)

        message.reply_text.assert_called_once()
        text = message.reply_text.call_args[0][0]
        assert "Obserwowane oferty" in text
        assert "Test Feedback Deal" in text


@pytest.mark.asyncio
async def test_cmd_target_adds_to_watchlist(tmp_path):
    """The /target command adds a deal to the watchlist."""
    db_path = tmp_path / "test.db"
    db = SQLiteStorage(db_path)

    # Seed a deal
    deal = type("Deal", (), {
        "id": "pepper:123", "title": "Test Deal", "price": 10000,
        "link": "https://example.com", "source": "pepper",
        "description": "", "image_url": "", "published_at": "",
        "regular_price": 0,
    })()
    db.upsert_deal(deal, profile="test", score=80, category="test")

    from feedback_bot import cmd_target

    update = MagicMock()
    update.effective_chat.id = 12345
    update.message.reply_html = AsyncMock()

    context = MagicMock()
    context.args = ["pepper:123", "8000"]

    with patch("feedback_bot.get_storage") as mock_storage:
        mock_storage.return_value.__enter__ = MagicMock(return_value=db)
        mock_storage.return_value.__exit__ = MagicMock(return_value=False)
        await cmd_target(update, context)

    update.message.reply_html.assert_called_once()
    msg = update.message.reply_html.call_args[0][0]
    assert "8" in msg  # target price mentioned

    items = db.get_watchlist()
    assert len(items) == 1
    assert items[0]["target_price"] == 8000
    db.close()


@pytest.mark.asyncio
async def test_cmd_target_missing_args():
    """The /target command with wrong args shows usage."""
    from feedback_bot import cmd_target

    update = MagicMock()
    update.effective_chat.id = 12345
    update.message.reply_html = AsyncMock()

    context = MagicMock()
    context.args = []

    await cmd_target(update, context)

    update.message.reply_html.assert_called_once()
    msg = update.message.reply_html.call_args[0][0]
    assert "/target" in msg.lower()
