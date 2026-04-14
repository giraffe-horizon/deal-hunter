"""Inline-keyboard callback query handler."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from deal_hunter.storage.database import get_session
from deal_hunter.storage.repositories import FeedbackRepository, OfferRepository


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline keyboard button presses (watch/skip) on deal alerts."""
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data
    if ":" not in data:
        await query.answer("Nieznana akcja")
        return

    action, deal_id = data.split(":", 1)

    if action not in ("watch", "skip"):
        await query.answer("Nieznana akcja")
        return

    with get_session() as session:
        status = "watching" if action == "watch" else "rejected"
        found = OfferRepository(session).update_status(deal_id, status)
        if not found:
            await query.answer("Nie znaleziono oferty w bazie")
            return

        FeedbackRepository(session).record(deal_id, action)

        if action == "watch":
            await query.answer("\u2b50 Dodano do obserwowanych")
        else:
            await query.answer("\U0001f44e Pominięto")
