#!/usr/bin/env python3
"""Telegram feedback bot — listens for inline keyboard callbacks and text commands.

Standalone process using python-telegram-bot v21+ (async polling).
Run: python feedback_bot.py
"""

import html
import logging
import os
import signal
import sys
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from storage.sqlite import SQLiteStorage

load_dotenv()

logging.basicConfig(
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("feedback_bot")

DB_PATH = Path("state/deals.db")


def get_storage() -> SQLiteStorage:
    """Get a SQLiteStorage instance."""
    return SQLiteStorage(DB_PATH)


# ── Callback query handler ──────────────────────────────────────────


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline keyboard button presses (watch/skip)."""
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

    storage = get_storage()
    try:
        status = "watching" if action == "watch" else "rejected"
        found = storage.update_deal_status(deal_id, status)
        if not found:
            await query.answer("Nie znaleziono oferty w bazie")
            return

        storage.record_feedback(deal_id, action)

        if action == "watch":
            await query.answer("\u2b50 Dodano do obserwowanych")
        else:
            await query.answer("\U0001f44e Pominięto")
    finally:
        storage.close()


# ── Text command handlers ────────────────────────────────────────────


async def cmd_watch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/watch <deal_id> — mark deal as watching."""
    if not context.args:
        await update.message.reply_text("Użycie: /watch <deal_id>")
        return

    deal_id = context.args[0]
    storage = get_storage()
    try:
        found = storage.update_deal_status(deal_id, "watching")
        if not found:
            await update.message.reply_text(f"Nie znaleziono oferty: {html.escape(deal_id)}")
            return
        storage.record_feedback(deal_id, "watch")
        await update.message.reply_text(
            f"\u2b50 Oferta {html.escape(deal_id)} dodana do obserwowanych"
        )
    finally:
        storage.close()


async def cmd_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/skip <deal_id> — mark deal as rejected."""
    if not context.args:
        await update.message.reply_text("Użycie: /skip <deal_id>")
        return

    deal_id = context.args[0]
    storage = get_storage()
    try:
        found = storage.update_deal_status(deal_id, "rejected")
        if not found:
            await update.message.reply_text(f"Nie znaleziono oferty: {html.escape(deal_id)}")
            return
        storage.record_feedback(deal_id, "skip")
        await update.message.reply_text(f"\U0001f44e Oferta {html.escape(deal_id)} pominięta")
    finally:
        storage.close()


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/status — show feedback summary."""
    storage = get_storage()
    try:
        stats = storage.get_feedback_stats()
        watching = len(storage.get_deals_by_status("watching", limit=10000))
        rejected = len(storage.get_deals_by_status("rejected", limit=10000))
        total = len(storage.get_deals())

        msg = "\U0001f4ca <b>Status bazy ofert</b>\n\n"
        msg += f"\u2b50 Obserwowane: <b>{watching}</b>\n"
        msg += f"\U0001f44e Pominięte: <b>{rejected}</b>\n"
        msg += f"\U0001f4e6 Łącznie w bazie: <b>{total}</b>\n"

        if stats:
            msg += "\n<b>Akcje feedback:</b>\n"
            for action, count in sorted(stats.items()):
                msg += f"  {action}: {count}\n"

        await update.message.reply_text(msg, parse_mode="HTML")
    finally:
        storage.close()


async def cmd_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/watchlist — show all deals with status='watching'."""
    storage = get_storage()
    try:
        deals = storage.get_deals_by_status("watching", limit=20)
        if not deals:
            await update.message.reply_text("Brak obserwowanych ofert.")
            return

        msg = f"\u2b50 <b>Obserwowane oferty ({len(deals)})</b>\n\n"
        for i, deal in enumerate(deals, 1):
            safe_title = html.escape(deal["title"][:80])
            price_str = f"{deal['price']:,} PLN".replace(",", " ") if deal["price"] else "brak ceny"
            link = html.escape(deal.get("link", ""))
            msg += f"{i}. <b>{safe_title}</b>\n"
            msg += f"   \U0001f4b0 {html.escape(price_str)}"
            if link:
                msg += f' | <a href="{link}">Link</a>'
            msg += "\n\n"

            if len(msg) > 3500:
                msg += "... i więcej ofert"
                break

        await update.message.reply_text(msg, parse_mode="HTML", disable_web_page_preview=True)
    finally:
        storage.close()


# ── Main ─────────────────────────────────────────────────────────────


def main() -> None:
    """Start the feedback bot."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not set in environment")
        sys.exit(1)

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(CommandHandler("watch", cmd_watch))
    app.add_handler(CommandHandler("skip", cmd_skip))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("watchlist", cmd_watchlist))

    logger.info("Feedback bot starting (polling)...")

    # Graceful shutdown on SIGTERM (systemd sends this)
    def handle_sigterm(signum, frame):
        logger.info("Received SIGTERM, shutting down...")
        app.stop_running()

    signal.signal(signal.SIGTERM, handle_sigterm)

    app.run_polling(drop_pending_updates=True)
    logger.info("Feedback bot stopped.")


if __name__ == "__main__":
    main()
