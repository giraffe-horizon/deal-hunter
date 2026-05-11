"""Inline keyboard builders for Telegram deal alerts."""

from __future__ import annotations

from deal_hunter.storage.models import compute_callback_token

_MAX_CALLBACK_DATA_LEN = 64
_SHORT_ID_PREFIX = "id:"


def make_callback_token(deal_id: str) -> str:
    """Return a stable short token for long deal ids."""
    return compute_callback_token(deal_id)


def build_callback_data(action: str, deal_id: str) -> str:
    """Build callback_data that always respects Telegram's 64-byte limit."""
    direct = f"{action}:{deal_id}"
    if len(direct.encode("utf-8")) <= _MAX_CALLBACK_DATA_LEN:
        return direct
    return f"{action}:{_SHORT_ID_PREFIX}{make_callback_token(deal_id)}"


def build_deal_keyboard(deal_link: str, deal_id: str, snooze_days: int = 30) -> dict:
    """Build inline keyboard for a deal alert.

    Two rows:
      Row 1 — Otwórz, Obserwuj, Skip (existing behavior).
      Row 2 — Drzemka <Nd>, Wycisz   (new: notification controls).
    """
    return {
        "inline_keyboard": [
            [
                {"text": "\U0001f517 Otwórz", "url": deal_link},
                {"text": "⭐ Obserwuj", "callback_data": build_callback_data("watch", deal_id)},
                {"text": "\U0001f44e Skip", "callback_data": build_callback_data("skip", deal_id)},
            ],
            [
                {
                    "text": f"\U0001f4a4 Drzemka {snooze_days}d",
                    "callback_data": build_callback_data("snooze", deal_id),
                },
                {
                    "text": "\U0001f515 Wycisz",
                    "callback_data": build_callback_data("mute", deal_id),
                },
            ],
        ]
    }
