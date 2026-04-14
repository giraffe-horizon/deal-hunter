"""Telegram notifier package.

Split into:

* ``transport.py`` — `TelegramNotifier` HTTP client with retry + rate limit
  and high-level ``send_*`` methods that delegate to formatters/keyboards.
* ``formatters.py`` — Polish-language HTML message formatters (pure, no I/O).
* ``keyboards.py`` — inline keyboard builders.

Public surface (unchanged from the old single-file module):

    from deal_hunter.notifiers.telegram import TelegramNotifier, build_deal_keyboard
"""

from deal_hunter.notifiers.telegram.formatters import (
    format_deal_alert,
    format_digest,
    format_price_drop,
    format_summary,
    format_watchlist_alert,
)
from deal_hunter.notifiers.telegram.keyboards import build_deal_keyboard

# Re-export `requests` and `time` so legacy `patch("deal_hunter.notifiers.telegram.requests")`
# / `patch("deal_hunter.notifiers.telegram.time")` call sites still work after the split.
from deal_hunter.notifiers.telegram.transport import TelegramNotifier, requests, time  # noqa: F401

__all__ = [
    "TelegramNotifier",
    "build_deal_keyboard",
    "format_deal_alert",
    "format_digest",
    "format_price_drop",
    "format_summary",
    "format_watchlist_alert",
]
