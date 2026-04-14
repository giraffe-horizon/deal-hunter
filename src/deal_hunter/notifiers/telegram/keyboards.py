"""Inline keyboard builders for Telegram deal alerts."""

from __future__ import annotations


def build_deal_keyboard(deal_link: str, deal_id: str) -> dict:
    """Build inline keyboard for a deal alert.

    Returns Telegram InlineKeyboardMarkup dict with Otwórz/Obserwuj/Skip buttons.
    """
    return {
        "inline_keyboard": [
            [
                {"text": "\U0001f517 Otwórz", "url": deal_link},
                {"text": "\u2b50 Obserwuj", "callback_data": f"watch:{deal_id}"},
                {"text": "\U0001f44e Skip", "callback_data": f"skip:{deal_id}"},
            ]
        ]
    }
