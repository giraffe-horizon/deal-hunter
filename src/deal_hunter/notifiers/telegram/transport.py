"""Telegram Bot API transport: HTTP with rate-limiting + retry.

`TelegramNotifier` is the canonical client. High-level ``send_*`` methods
compose a message via formatters/keyboards and hand it to the private
``_send_message`` / ``send_photo`` transport methods.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

import requests

from deal_hunter.notifiers.telegram.formatters import (
    format_deal_alert,
    format_digest,
    format_price_drop,
    format_summary,
    format_watchlist_alert,
)
from deal_hunter.notifiers.telegram.keyboards import build_deal_keyboard
from deal_hunter.notifiers.telegram.recorder import record_sent_notification

if TYPE_CHECKING:
    from deal_hunter.sources.base import Deal

logger = logging.getLogger(__name__)

_RATE_LIMIT_SLEEP = 1.5
_DEFAULT_RETRY_AFTER = 30
_MAX_ATTEMPTS = 3


class TelegramNotifier:
    """Sends deal alerts to Telegram with rate limiting and retry."""

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    # ── High-level senders (compose via formatters + dispatch via transport) ──

    def send_alert(
        self,
        deal: Deal,
        score: int,
        tier: str,
        plus: list[str],
        minus: list[str],
        topic_id: int | None = None,
        emoji: str = "\U0001f525",
        size_warning: str = "",
        currency: str = "PLN",
        snooze_days: int = 30,
        profile: str | None = None,
    ) -> None:
        """Send individual deal alert (messages in Polish for end users)."""
        msg = format_deal_alert(
            deal,
            score,
            tier,
            plus,
            minus,
            emoji=emoji,
            size_warning=size_warning,
            currency=currency,
        )
        keyboard = build_deal_keyboard(deal.link, deal.id, snooze_days=snooze_days)
        if self._send_message(msg, topic_id=topic_id, reply_markup=keyboard):
            record_sent_notification(
                alert_type="deal",
                payload={
                    "title": deal.title,
                    "price": deal.price,
                    "link": deal.link,
                    "score": score,
                    "plus": list(plus)[:6],
                    "minus": list(minus)[:4],
                },
                deal_id=deal.id,
                profile=profile,
            )

    def send_summary(
        self,
        remaining_alerts: list[dict],
        topic_id: int | None = None,
        emoji: str = "\U0001f525",
        currency: str = "PLN",
        profile: str | None = None,
    ) -> None:
        """Send summary message for overflow alerts (messages in Polish for end users)."""
        msg = format_summary(remaining_alerts, emoji=emoji, currency=currency)
        if not msg:
            return
        if self._send_message(msg, topic_id=topic_id, disable_preview=True):
            sample_titles: list[str] = []
            for a in remaining_alerts[:5]:
                deal = a.get("deal")
                title = getattr(deal, "title", "") if deal is not None else ""
                sample_titles.append(title)
            record_sent_notification(
                alert_type="summary",
                payload={
                    "remaining_count": len(remaining_alerts),
                    "sample_titles": sample_titles,
                },
                profile=profile,
            )

    def send_price_drop_alert(
        self,
        deal: Deal,
        price_change: dict,
        topic_id: int | None = None,
        emoji: str = "\U0001f50d",
        currency: str = "PLN",
        snooze_days: int = 30,
        profile: str | None = None,
    ) -> None:
        """Send a price drop alert (messages in Polish for end users)."""
        msg = format_price_drop(deal, price_change, emoji=emoji, currency=currency)
        keyboard = build_deal_keyboard(deal.link, deal.id, snooze_days=snooze_days)
        if self._send_message(msg, topic_id=topic_id, reply_markup=keyboard):
            record_sent_notification(
                alert_type="price_drop",
                payload={
                    "title": deal.title,
                    "link": deal.link,
                    "old_price": price_change.get("old_price"),
                    "new_price": price_change.get("new_price"),
                    "diff_pln": price_change.get("diff_pln"),
                    "diff_percent": price_change.get("diff_percent"),
                    "is_lowest_ever": bool(price_change.get("is_lowest_ever")),
                },
                deal_id=deal.id,
                profile=profile,
            )

    def send_watchlist_alert(
        self,
        deal: Deal,
        target_price: int,
        current_price: int,
        topic_id: int | None = None,
        currency: str = "PLN",
        snooze_days: int = 30,
        profile: str | None = None,
    ) -> None:
        """Send watchlist target price alert (messages in Polish for end users)."""
        msg = format_watchlist_alert(deal, target_price, current_price, currency=currency)
        keyboard = build_deal_keyboard(deal.link, deal.id, snooze_days=snooze_days)
        if self._send_message(msg, topic_id=topic_id, reply_markup=keyboard):
            record_sent_notification(
                alert_type="watchlist",
                payload={
                    "title": deal.title,
                    "target_price": target_price,
                    "current_price": current_price,
                },
                deal_id=deal.id,
                profile=profile,
            )

    def send_digest(
        self,
        drops: list[dict],
        topic_id: int | None = None,
        emoji: str = "\U0001f4ca",
        currency: str = "PLN",
    ) -> None:
        """Send weekly price digest (messages in Polish for end users)."""
        msg = format_digest(drops, emoji=emoji, currency=currency)
        if not msg:
            return
        if self._send_message(msg, topic_id=topic_id, disable_preview=True):
            # Store only a small shape per drop — keeps the row size bounded.
            top_drops = [
                {
                    "id": d.get("id"),
                    "title": (d.get("title") or "")[:120],
                    "old_price": d.get("old_price"),
                    "new_price": d.get("new_price"),
                    "diff_percent": d.get("diff_percent"),
                    "is_lowest_ever": bool(d.get("is_lowest_ever")),
                }
                for d in drops[:10]
            ]
            record_sent_notification(
                alert_type="digest",
                payload={"drop_count": len(drops), "top_drops": top_drops},
                deal_id=None,
                profile=None,
            )

    def send_text(self, text: str, topic_id: int | None = None) -> bool:
        """Send a plain text message, optionally to a specific topic."""
        return self._send_message(text, topic_id=topic_id)

    # ── Transport ──

    def send_photo(
        self,
        photo_path: str,
        caption: str = "",
        topic_id: int | None = None,
    ) -> bool:
        """Send a photo via Telegram sendPhoto (multipart/form-data upload).

        Returns True iff the API returned 200.
        """
        url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"
        data = {"chat_id": self.chat_id}
        if caption:
            data["caption"] = caption
            data["parse_mode"] = "HTML"
        if topic_id:
            data["message_thread_id"] = str(topic_id)

        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                time.sleep(_RATE_LIMIT_SLEEP)
                with Path(photo_path).open("rb") as f:
                    resp = requests.post(url, data=data, files={"photo": f}, timeout=30)
                if resp.status_code == 200:
                    logger.info(f"Telegram: sent photo {photo_path}")
                    return True
                if resp.status_code == 429:
                    retry_after = self._retry_after(resp)
                    logger.warning(
                        f"Telegram: rate limited on photo, waiting {retry_after}s"
                        f" (attempt {attempt}/{_MAX_ATTEMPTS})"
                    )
                    if attempt < _MAX_ATTEMPTS:
                        time.sleep(retry_after)
                        continue
                else:
                    logger.error(f"Telegram sendPhoto: HTTP {resp.status_code}: {resp.text[:200]}")
                    if attempt < _MAX_ATTEMPTS:
                        continue
            except Exception as e:
                logger.error(
                    f"Telegram sendPhoto: exception (attempt {attempt}/{_MAX_ATTEMPTS}): {e}"
                )
                if attempt < _MAX_ATTEMPTS:
                    continue

        logger.error("Telegram: failed to send photo after 3 attempts")
        return False

    def _send_message(
        self,
        text: str,
        topic_id: int | None = None,
        disable_preview: bool = False,
        reply_markup: dict | None = None,
    ) -> bool:
        """Send message with retry and rate limiting. Returns True iff the API returned 200."""
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": disable_preview,
        }
        if topic_id:
            payload["message_thread_id"] = topic_id
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)

        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                time.sleep(_RATE_LIMIT_SLEEP)
                resp = requests.post(self.api_url, json=payload, timeout=10)
                if resp.status_code == 200:
                    logger.info(f"Telegram: sent message ({len(text)} chars)")
                    return True
                if resp.status_code == 429:
                    retry_after = self._retry_after(resp)
                    logger.warning(
                        f"Telegram: rate limited, waiting {retry_after}s"
                        f" (attempt {attempt}/{_MAX_ATTEMPTS})"
                    )
                    if attempt < _MAX_ATTEMPTS:
                        time.sleep(retry_after)
                        continue
                else:
                    logger.error(f"Telegram: HTTP {resp.status_code}: {resp.text[:200]}")
                    if attempt < _MAX_ATTEMPTS:
                        continue
            except Exception as e:
                logger.error(f"Telegram: exception (attempt {attempt}/{_MAX_ATTEMPTS}): {e}")
                if attempt < _MAX_ATTEMPTS:
                    continue

        logger.error("Telegram: failed to send after 3 attempts")
        return False

    @staticmethod
    def _retry_after(resp: requests.Response) -> int:
        """Extract retry_after from a 429 response body; fall back to default."""
        try:
            return int(resp.json().get("parameters", {}).get("retry_after", _DEFAULT_RETRY_AFTER))
        except (ValueError, KeyError, TypeError):
            return _DEFAULT_RETRY_AFTER
