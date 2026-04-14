#!/usr/bin/env python3
"""Telegram feedback bot — entrypoint.

Standalone process using python-telegram-bot v21+ (async polling).
Handlers live in ``bot.callbacks`` (inline keyboards) and ``bot.commands``
(slash commands); this module just wires them into an Application and
handles signals.

Handler functions are re-exported at package level for backwards
compatibility with existing ``from deal_hunter.bot.main import ...`` imports.
"""

from __future__ import annotations

import logging
import signal
import sys

from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler

from deal_hunter.bot.callbacks import handle_callback
from deal_hunter.bot.commands import cmd_skip, cmd_status, cmd_target, cmd_watch, cmd_watchlist
from deal_hunter.core.logging import setup_bot_logging
from deal_hunter.core.settings import get_settings

setup_bot_logging()
logger = logging.getLogger("feedback_bot")

# Re-exports — tests import these from `deal_hunter.bot.main`.
__all__ = [
    "cmd_skip",
    "cmd_status",
    "cmd_target",
    "cmd_watch",
    "cmd_watchlist",
    "handle_callback",
    "main",
]


def main() -> None:
    """Start the feedback bot."""
    token = get_settings().telegram_bot_token
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not set in environment")
        sys.exit(1)

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(CommandHandler("watch", cmd_watch))
    app.add_handler(CommandHandler("skip", cmd_skip))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("watchlist", cmd_watchlist))
    app.add_handler(CommandHandler("target", cmd_target))

    logger.info("Feedback bot starting (polling)...")

    # Graceful shutdown on SIGTERM (systemd sends this)
    def handle_sigterm(signum, frame):  # type: ignore[no-untyped-def]
        logger.info("Received SIGTERM, shutting down...")
        app.stop_running()

    signal.signal(signal.SIGTERM, handle_sigterm)

    app.run_polling(drop_pending_updates=True)
    logger.info("Feedback bot stopped.")


if __name__ == "__main__":
    main()
