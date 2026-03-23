"""Telegram notifier with retry and rate limiting."""

import time
import logging

import requests

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Sends deal alerts to Telegram with rate limiting and retry."""

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    def send_alert(self, deal, score: int, tier: str, plus: list[str], minus: list[str],
                   topic_id: int | None = None, emoji: str = "\U0001f525",
                   size_warning: str = "", currency: str = "PLN") -> None:
        """Send individual deal alert (messages in Polish for end users)."""
        price_str = f"{deal.price:,} {currency}".replace(',', ' ') if deal.price > 0 else "brak ceny"

        msg = f"*{tier}* (score: {score})\n"
        msg += f"{emoji} *{deal.title}*\n"
        msg += f"\U0001f4b0 Cena: *{price_str}*\n\n"

        plus_with_warning = list(plus)
        if size_warning:
            plus_with_warning.append(size_warning)

        if plus_with_warning:
            msg += f"\u2705 {', '.join(plus_with_warning[:6])}\n"
        if minus:
            msg += f"\u26a0\ufe0f {', '.join(minus[:4])}\n"

        msg += f"\n\U0001f517 [LINK DO OKAZJI]({deal.link}) | \u0179r\u00f3d\u0142o: {deal.source}"

        self._send_message(msg, topic_id=topic_id)

    def send_summary(self, remaining_alerts: list[dict], topic_id: int | None = None,
                     emoji: str = "\U0001f525", currency: str = "PLN") -> None:
        """Send summary message for overflow alerts (messages in Polish for end users)."""
        if not remaining_alerts:
            return

        msg = f"{emoji} PODSUMOWANIE - {len(remaining_alerts)} dodatkowych ofert:\n\n"

        for i, alert in enumerate(remaining_alerts, 1):
            deal = alert['deal']
            score = alert['score']
            price_str = f"{deal.price:,} {currency}".replace(',', ' ') if deal.price > 0 else "brak ceny"

            msg += f"{i}. *{deal.title[:80]}*\n"
            msg += f"   \U0001f4b0 {price_str} | Score: {score}\n"
            msg += f"   \U0001f517 [Link]({deal.link}) | {deal.source}\n\n"

            if len(msg) > 3500:
                msg += f"... i {len(remaining_alerts) - i} wi\u0119cej ofert"
                break

        self._send_message(msg, topic_id=topic_id, disable_preview=True)

    def _send_message(self, text: str, topic_id: int | None = None,
                      disable_preview: bool = False) -> None:
        """Send message with retry and rate limiting."""
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": disable_preview,
        }
        if topic_id:
            payload["message_thread_id"] = topic_id

        for attempt in range(1, 4):
            try:
                time.sleep(1.5)  # Rate limiting
                resp = requests.post(self.api_url, json=payload, timeout=10)
                if resp.status_code == 200:
                    logger.info(f"Telegram: sent message ({len(text)} chars)")
                    return
                elif resp.status_code == 429:
                    retry_after = resp.json().get('parameters', {}).get('retry_after', 30)
                    logger.warning(f"Telegram: rate limited, waiting {retry_after}s (attempt {attempt}/3)")
                    if attempt < 3:
                        time.sleep(retry_after)
                        continue
                else:
                    logger.error(f"Telegram: HTTP {resp.status_code}: {resp.text[:200]}")
                    if attempt < 3:
                        continue
            except Exception as e:
                logger.error(f"Telegram: exception (attempt {attempt}/3): {e}")
                if attempt < 3:
                    continue

        logger.error("Telegram: failed to send after 3 attempts")
