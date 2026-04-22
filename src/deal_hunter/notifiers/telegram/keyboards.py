"""Inline keyboard builders for Telegram deal alerts."""

from __future__ import annotations

import hashlib

_MAX_CALLBACK_DATA_LEN = 64
_SHORT_ID_PREFIX = "id:"
_SHORT_ID_DIGEST_BYTES = 8


def make_callback_token(deal_id: str) -> str:
    """Return a stable short token for long deal ids."""
    return hashlib.blake2s(deal_id.encode("utf-8"), digest_size=_SHORT_ID_DIGEST_BYTES).hexdigest()


def build_callback_data(action: str, deal_id: str) -> str:
    """Build callback_data that always respects Telegram's 64-byte limit."""
    direct = f"{action}:{deal_id}"
    if len(direct.encode("utf-8")) <= _MAX_CALLBACK_DATA_LEN:
        return direct
    return f"{action}:{_SHORT_ID_PREFIX}{make_callback_token(deal_id)}"


def build_deal_keyboard(deal_link: str, deal_id: str) -> dict:
    """Build inline keyboard for a deal alert.

    Returns Telegram InlineKeyboardMarkup dict with Otwórz/Obserwuj/Skip buttons.
    """
    return {
        "inline_keyboard": [
            [
                {"text": "\U0001f517 Otwórz", "url": deal_link},
                {"text": "\u2b50 Obserwuj", "callback_data": build_callback_data("watch", deal_id)},
                {"text": "\U0001f44e Skip", "callback_data": build_callback_data("skip", deal_id)},
            ]
        ]
    }
