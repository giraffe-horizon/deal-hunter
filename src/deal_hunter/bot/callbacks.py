"""Inline-keyboard callback query handler."""

from __future__ import annotations

from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import ContextTypes

from deal_hunter.core.notification_config import load_global_config
from deal_hunter.core.settings import get_settings
from deal_hunter.storage.database import get_session
from deal_hunter.storage.repositories import FeedbackRepository, OfferRepository

PERMANENT_MUTE_SENTINEL = "9999-12-31T00:00:00"


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline keyboard button presses on deal alerts."""
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data
    if ":" not in data:
        await query.answer("Nieznana akcja")
        return

    action, deal_ref = data.split(":", 1)

    if action not in ("watch", "skip", "mute", "snooze"):
        await query.answer("Nieznana akcja")
        return

    with get_session() as session:
        repo = OfferRepository(session)
        deal_id = repo.resolve_callback_deal_id(deal_ref)
        if not deal_id:
            await query.answer("Nie znaleziono oferty w bazie")
            return

        if action == "watch":
            if not repo.update_status(deal_id, "watching"):
                await query.answer("Nie znaleziono oferty w bazie")
                return
            FeedbackRepository(session).record(deal_id, action)
            await query.answer("⭐ Dodano do obserwowanych")
            return

        if action == "skip":
            if not repo.update_status(deal_id, "rejected"):
                await query.answer("Nie znaleziono oferty w bazie")
                return
            FeedbackRepository(session).record(deal_id, action)
            await query.answer("\U0001f44e Pominięto")
            return

        if action == "mute":
            if not repo.set_muted_until(deal_id, PERMANENT_MUTE_SENTINEL):
                await query.answer("Nie znaleziono oferty w bazie")
                return
            FeedbackRepository(session).record(deal_id, "mute")
            await query.answer("\U0001f515 Wyciszono")
            return

        if action == "snooze":
            cfg = load_global_config(get_settings().base_dir / "config" / "notifications.yaml")
            until = (datetime.now() + timedelta(days=cfg.default_snooze_days)).isoformat()
            if not repo.set_muted_until(deal_id, until):
                await query.answer("Nie znaleziono oferty w bazie")
                return
            FeedbackRepository(session).record(deal_id, "snooze")
            await query.answer(
                f"\U0001f4a4 Wyciszono do {datetime.fromisoformat(until).strftime('%d.%m.%Y')}"
            )
            return
