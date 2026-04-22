"""Tests for Telegram feedback bot — SQLAlchemy repos, callback parsing, inline keyboard."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from deal_hunter.notifiers.telegram import build_deal_keyboard
from deal_hunter.notifiers.telegram.keyboards import build_callback_data
from deal_hunter.sources.base import Deal
from deal_hunter.storage.models import Base
from deal_hunter.storage.repositories import (
    FeedbackRepository,
    WatchlistRepository,
)
from deal_hunter.storage.repositories import (
    OfferRepository as DealRepository,
)

# ── Fixtures ─────────────────────────────────────────────────────────


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
def deal_repo(session):
    return DealRepository(session)


@pytest.fixture
def feedback_repo(session):
    return FeedbackRepository(session)


def _seed_deal(session, deal_id="pepper:77777", price=5000, profile="test", score=100):
    """Insert a deal using the repository."""
    deal_repo = DealRepository(session)
    deal_repo.upsert(
        id=deal_id,
        title="Test Feedback Deal",
        price=price,
        link=f"https://example.com/deal/{deal_id}",
        source="pepper",
        description="A test deal for feedback",
        image_url="",
        profile=profile,
        score=score,
    )
    session.flush()


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


# ── Repository-level tests ──────────────────────────────────────────


class TestUpdateDealStatus:
    def test_update_existing_deal(self, session, deal_repo):
        _seed_deal(session)
        result = deal_repo.update_status("pepper:77777", "watching")
        assert result is True
        session.flush()
        row = deal_repo.get_by_id("pepper:77777")
        assert row["status"] == "watching"

    def test_update_nonexistent_deal(self, deal_repo):
        result = deal_repo.update_status("nonexistent:000", "watching")
        assert result is False

    def test_update_to_rejected(self, session, deal_repo):
        _seed_deal(session)
        deal_repo.update_status("pepper:77777", "rejected")
        session.flush()
        row = deal_repo.get_by_id("pepper:77777")
        assert row["status"] == "rejected"


class TestGetDealsByStatus:
    def test_filter_watching(self, session, deal_repo):
        _seed_deal(session, "pepper:77777")
        _seed_deal(session, "ceneo:66666")
        deal_repo.update_status("pepper:77777", "watching")
        session.flush()

        watching = deal_repo.get_by_status("watching")
        assert len(watching) == 1
        assert watching[0]["id"] == "pepper:77777"

    def test_empty_result(self, session, deal_repo):
        _seed_deal(session)
        assert deal_repo.get_by_status("watching") == []

    def test_limit(self, session, deal_repo):
        for i in range(5):
            _seed_deal(session, f"test:{i}")
            deal_repo.update_status(f"test:{i}", "watching")
        session.flush()

        result = deal_repo.get_by_status("watching", limit=3)
        assert len(result) == 3


class TestGetFeedbackStats:
    def test_empty_stats(self, feedback_repo):
        assert feedback_repo.get_stats() == {}

    def test_counts_per_action(self, session, feedback_repo):
        _seed_deal(session)
        feedback_repo.record("pepper:77777", "watch")
        feedback_repo.record("pepper:77777", "watch")
        feedback_repo.record("pepper:77777", "skip")
        session.flush()

        stats = feedback_repo.get_stats()
        assert stats["watch"] == 2
        assert stats["skip"] == 1

    def test_multiple_deals(self, session, feedback_repo):
        _seed_deal(session, "pepper:77777")
        _seed_deal(session, "ceneo:66666")
        feedback_repo.record("pepper:77777", "watch")
        feedback_repo.record("ceneo:66666", "skip")
        session.flush()

        stats = feedback_repo.get_stats()
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

    def test_long_deal_id_is_shortened_for_callback_limit(self):
        long_id = "rowertour:Rower_gravel_Cannondale_Topstone_Carbon_3_GRX_1x12"
        callback = build_callback_data("watch", long_id)
        assert len(callback.encode("utf-8")) <= 64
        assert callback.startswith("watch:id:")


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
    async def test_handle_callback_watch(self, engine):
        from deal_hunter.bot.main import handle_callback

        # Seed a deal using a session
        with Session(engine) as session:
            _seed_deal(session)
            session.commit()

        query = AsyncMock()
        query.data = "watch:pepper:77777"
        update = MagicMock()
        update.callback_query = query
        context = MagicMock()

        # Mock get_session to use our engine
        from contextlib import contextmanager

        @contextmanager
        def _mock_session():
            with Session(engine) as s:
                yield s
                s.commit()

        with patch("deal_hunter.bot.callbacks.get_session", _mock_session):
            await handle_callback(update, context)

        query.answer.assert_called_once_with("\u2b50 Dodano do obserwowanych")

        # Verify status updated
        with Session(engine) as s:
            deal = DealRepository(s).get_by_id("pepper:77777")
            assert deal["status"] == "watching"

    @pytest.mark.asyncio
    async def test_handle_callback_skip(self, engine):
        from deal_hunter.bot.main import handle_callback

        with Session(engine) as session:
            _seed_deal(session)
            session.commit()

        query = AsyncMock()
        query.data = "skip:pepper:77777"
        update = MagicMock()
        update.callback_query = query
        context = MagicMock()

        from contextlib import contextmanager

        @contextmanager
        def _mock_session():
            with Session(engine) as s:
                yield s
                s.commit()

        with patch("deal_hunter.bot.callbacks.get_session", _mock_session):
            await handle_callback(update, context)

        query.answer.assert_called_once_with("\U0001f44e Pominięto")

        with Session(engine) as s:
            deal = DealRepository(s).get_by_id("pepper:77777")
            assert deal["status"] == "rejected"

    @pytest.mark.asyncio
    async def test_handle_callback_unknown_deal(self, engine):
        from deal_hunter.bot.main import handle_callback

        query = AsyncMock()
        query.data = "watch:nonexistent:000"
        update = MagicMock()
        update.callback_query = query
        context = MagicMock()

        from contextlib import contextmanager

        @contextmanager
        def _mock_session():
            with Session(engine) as s:
                yield s
                s.commit()

        with patch("deal_hunter.bot.callbacks.get_session", _mock_session):
            await handle_callback(update, context)

        query.answer.assert_called_once_with("Nie znaleziono oferty w bazie")

    @pytest.mark.asyncio
    async def test_handle_callback_watch_with_shortened_deal_id(self, engine):
        from deal_hunter.bot.main import handle_callback

        long_id = "rowertour:Rower_gravel_Cannondale_Topstone_Carbon_3_GRX_1x12"
        with Session(engine) as session:
            _seed_deal(session, deal_id=long_id)
            session.commit()

        query = AsyncMock()
        query.data = build_callback_data("watch", long_id)
        update = MagicMock()
        update.callback_query = query
        context = MagicMock()

        from contextlib import contextmanager

        @contextmanager
        def _mock_session():
            with Session(engine) as s:
                yield s
                s.commit()

        with patch("deal_hunter.bot.callbacks.get_session", _mock_session):
            await handle_callback(update, context)

        query.answer.assert_called_once_with("\u2b50 Dodano do obserwowanych")

        with Session(engine) as s:
            deal = DealRepository(s).get_by_id(long_id)
            assert deal["status"] == "watching"

    @pytest.mark.asyncio
    async def test_cmd_status(self, engine):
        from deal_hunter.bot.main import cmd_status

        with Session(engine) as session:
            _seed_deal(session)
            FeedbackRepository(session).record("pepper:77777", "watch")
            session.commit()

        message = AsyncMock()
        update = MagicMock()
        update.message = message
        context = MagicMock()

        from contextlib import contextmanager

        @contextmanager
        def _mock_session():
            with Session(engine) as s:
                yield s
                s.commit()

        with patch("deal_hunter.bot.commands.get_session", _mock_session):
            await cmd_status(update, context)

        message.reply_text.assert_called_once()
        text = message.reply_text.call_args[0][0]
        assert "Status bazy ofert" in text

    @pytest.mark.asyncio
    async def test_cmd_watchlist_empty(self, engine):
        from deal_hunter.bot.main import cmd_watchlist

        message = AsyncMock()
        update = MagicMock()
        update.message = message
        context = MagicMock()

        from contextlib import contextmanager

        @contextmanager
        def _mock_session():
            with Session(engine) as s:
                yield s
                s.commit()

        with patch("deal_hunter.bot.commands.get_session", _mock_session):
            await cmd_watchlist(update, context)

        message.reply_text.assert_called_once_with("Brak obserwowanych ofert.")

    @pytest.mark.asyncio
    async def test_cmd_watchlist_with_deals(self, engine):
        from deal_hunter.bot.main import cmd_watchlist

        with Session(engine) as session:
            _seed_deal(session)
            DealRepository(session).update_status("pepper:77777", "watching")
            session.commit()

        message = AsyncMock()
        update = MagicMock()
        update.message = message
        context = MagicMock()

        from contextlib import contextmanager

        @contextmanager
        def _mock_session():
            with Session(engine) as s:
                yield s
                s.commit()

        with patch("deal_hunter.bot.commands.get_session", _mock_session):
            await cmd_watchlist(update, context)

        message.reply_text.assert_called_once()
        text = message.reply_text.call_args[0][0]
        assert "Obserwowane oferty" in text
        assert "Test Feedback Deal" in text


@pytest.mark.asyncio
async def test_cmd_target_adds_to_watchlist():
    """The /target command adds a deal to the watchlist."""
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)

    # Seed a deal
    with Session(eng) as session:
        _seed_deal(session, "pepper:123", price=10000)
        session.commit()

    from deal_hunter.bot.main import cmd_target

    update = MagicMock()
    update.effective_chat.id = 12345
    update.message.reply_html = AsyncMock()

    context = MagicMock()
    context.args = ["pepper:123", "8000"]

    from contextlib import contextmanager

    @contextmanager
    def _mock_session():
        with Session(eng) as s:
            yield s
            s.commit()

    with patch("deal_hunter.bot.commands.get_session", _mock_session):
        await cmd_target(update, context)

    update.message.reply_html.assert_called_once()
    msg = update.message.reply_html.call_args[0][0]
    assert "8" in msg  # target price mentioned

    with Session(eng) as session:
        items = WatchlistRepository(session).get_all()
        assert len(items) == 1
        assert items[0]["target_price"] == 8000


@pytest.mark.asyncio
async def test_cmd_target_missing_args():
    """The /target command with wrong args shows usage."""
    from deal_hunter.bot.main import cmd_target

    update = MagicMock()
    update.effective_chat.id = 12345
    update.message.reply_html = AsyncMock()

    context = MagicMock()
    context.args = []

    await cmd_target(update, context)

    update.message.reply_html.assert_called_once()
    msg = update.message.reply_html.call_args[0][0]
    assert "/target" in msg.lower()
