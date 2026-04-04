"""Telegram notifier with retry and rate limiting."""

import html
import json
import logging
import time

import requests

logger = logging.getLogger(__name__)


def build_deal_keyboard(deal_link: str, deal_id: str) -> dict:
    """Build inline keyboard for a deal alert.

    Returns Telegram InlineKeyboardMarkup dict.
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


class TelegramNotifier:
    """Sends deal alerts to Telegram with rate limiting and retry."""

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    def send_alert(
        self,
        deal,
        score: int,
        tier: str,
        plus: list[str],
        minus: list[str],
        topic_id: int | None = None,
        emoji: str = "\U0001f525",
        size_warning: str = "",
        currency: str = "PLN",
    ) -> None:
        """Send individual deal alert (messages in Polish for end users)."""
        price_str = (
            f"{deal.price:,} {currency}".replace(",", " ") if deal.price > 0 else "brak ceny"
        )

        safe_title = html.escape(deal.title)
        safe_tier = html.escape(tier)

        msg = f"<b>{safe_tier}</b> (score: {score})\n"
        msg += f"{emoji} <b>{safe_title}</b>\n"

        if deal.regular_price > 0 and deal.price > 0:
            regular_str = f"{deal.regular_price:,} {currency}".replace(",", " ")
            discount = round((deal.regular_price - deal.price) / deal.regular_price * 100)
            msg += f"\U0001f4b0 Cena: <b>{html.escape(price_str)}</b> <s>{html.escape(regular_str)}</s> (-{discount}%)\n\n"
        else:
            msg += f"\U0001f4b0 Cena: <b>{html.escape(price_str)}</b>\n\n"

        plus_with_warning = list(plus)
        if size_warning:
            plus_with_warning.append(size_warning)

        if plus_with_warning:
            safe_plus = [html.escape(p) for p in plus_with_warning[:6]]
            msg += f"\u2705 {', '.join(safe_plus)}\n"
        if minus:
            safe_minus = [html.escape(m) for m in minus[:4]]
            msg += f"\u26a0\ufe0f {', '.join(safe_minus)}\n"

        safe_link = html.escape(deal.link)
        safe_source = html.escape(deal.source)
        msg += f'\n\U0001f517 <a href="{safe_link}">LINK DO OKAZJI</a> | \u0179r\u00f3d\u0142o: {safe_source}'

        keyboard = build_deal_keyboard(deal.link, deal.id)
        self._send_message(msg, topic_id=topic_id, reply_markup=keyboard)

    def send_summary(
        self,
        remaining_alerts: list[dict],
        topic_id: int | None = None,
        emoji: str = "\U0001f525",
        currency: str = "PLN",
    ) -> None:
        """Send summary message for overflow alerts (messages in Polish for end users)."""
        if not remaining_alerts:
            return

        msg = f"{emoji} PODSUMOWANIE - {len(remaining_alerts)} dodatkowych ofert:\n\n"

        for i, alert in enumerate(remaining_alerts, 1):
            deal = alert["deal"]
            score = alert["score"]
            price_str = (
                f"{deal.price:,} {currency}".replace(",", " ") if deal.price > 0 else "brak ceny"
            )

            safe_title = html.escape(deal.title[:80])
            safe_link = html.escape(deal.link)
            safe_source = html.escape(deal.source)
            msg += f"{i}. <b>{safe_title}</b>\n"
            msg += f"   \U0001f4b0 {html.escape(price_str)} | Score: {score}\n"
            msg += f'   \U0001f517 <a href="{safe_link}">Link</a> | {safe_source}\n\n'

            if len(msg) > 3500:
                msg += f"... i {len(remaining_alerts) - i} wi\u0119cej ofert"
                break

        self._send_message(msg, topic_id=topic_id, disable_preview=True)

    def send_price_drop_alert(
        self,
        deal,
        price_change: dict,
        topic_id: int | None = None,
        emoji: str = "\U0001f50d",
        currency: str = "PLN",
    ) -> None:
        """Send a price drop alert (messages in Polish for end users)."""
        old_str = f"{price_change['old_price']:,} {currency}".replace(",", " ")
        new_str = f"{price_change['new_price']:,} {currency}".replace(",", " ")
        diff_pln = price_change["diff_pln"]
        diff_pct = price_change["diff_percent"]
        diff_pln_str = f"{diff_pln:,}".replace(",", " ")

        safe_title = html.escape(deal.title)
        safe_link = html.escape(deal.link)
        safe_source = html.escape(deal.source)

        msg = f"{emoji} \U0001f4c9 <b>SPADEK CENY!</b>\n"
        msg += f"<b>{safe_title}</b>\n"
        msg += f"{html.escape(old_str)} \u2192 <b>{html.escape(new_str)}</b> (-{diff_pct:.0f}%, -{html.escape(diff_pln_str)} {html.escape(currency)})\n"

        if price_change.get("is_lowest_ever"):
            msg += "\U0001f525 <b>Najni\u017csza cena w historii!</b>\n"

        msg += f'\n\U0001f517 <a href="{safe_link}">Link do oferty</a> | \u0179r\u00f3d\u0142o: {safe_source}'

        keyboard = build_deal_keyboard(deal.link, deal.id)
        self._send_message(msg, topic_id=topic_id, reply_markup=keyboard)

    def send_digest(
        self,
        drops: list[dict],
        topic_id: int | None = None,
        emoji: str = "\U0001f4ca",
        currency: str = "PLN",
    ) -> None:
        """Send weekly price digest (messages in Polish for end users)."""
        if not drops:
            return

        msg = f"{emoji} <b>Tygodniowy przegl\u0105d cen ({len(drops)} spadk\u00f3w)</b>\n\n"

        for drop in drops:
            safe_title = html.escape(drop["title"][:80])
            old_str = f"{drop['old_price']:,}".replace(",", " ")
            new_str = f"{drop['new_price']:,}".replace(",", " ")
            diff_pct = drop["diff_percent"]

            msg += f"\U0001f4c9 {safe_title}: {html.escape(old_str)} \u2192 {html.escape(new_str)} {html.escape(currency)} (-{diff_pct:.0f}%)"
            if drop.get("is_lowest_ever"):
                msg += " \U0001f525"
            msg += "\n"

            if len(msg) > 3500:
                msg += f"\n... i wi\u0119cej spadk\u00f3w"
                break

        self._send_message(msg, topic_id=topic_id, disable_preview=True)

    def send_photo(
        self,
        photo_path: str,
        caption: str = "",
        topic_id: int | None = None,
    ) -> None:
        """Send a photo via Telegram sendPhoto (multipart/form-data upload)."""
        url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"
        data = {"chat_id": self.chat_id}
        if caption:
            data["caption"] = caption
            data["parse_mode"] = "HTML"
        if topic_id:
            data["message_thread_id"] = str(topic_id)

        for attempt in range(1, 4):
            try:
                time.sleep(1.5)  # Rate limiting
                with open(photo_path, "rb") as f:
                    resp = requests.post(
                        url, data=data, files={"photo": f}, timeout=30
                    )
                if resp.status_code == 200:
                    logger.info(f"Telegram: sent photo {photo_path}")
                    return
                elif resp.status_code == 429:
                    try:
                        retry_after = resp.json().get("parameters", {}).get("retry_after", 30)
                    except (ValueError, KeyError):
                        retry_after = 30
                    logger.warning(
                        f"Telegram: rate limited on photo, waiting {retry_after}s (attempt {attempt}/3)"
                    )
                    if attempt < 3:
                        time.sleep(retry_after)
                        continue
                else:
                    logger.error(f"Telegram sendPhoto: HTTP {resp.status_code}: {resp.text[:200]}")
                    if attempt < 3:
                        continue
            except Exception as e:
                logger.error(f"Telegram sendPhoto: exception (attempt {attempt}/3): {e}")
                if attempt < 3:
                    continue

        logger.error("Telegram: failed to send photo after 3 attempts")

    def send_text(self, text: str, topic_id: int | None = None) -> None:
        """Send a plain text message, optionally to a specific topic."""
        self._send_message(text, topic_id=topic_id)

    def _send_message(
        self,
        text: str,
        topic_id: int | None = None,
        disable_preview: bool = False,
        reply_markup: dict | None = None,
    ) -> None:
        """Send message with retry and rate limiting."""
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

        for attempt in range(1, 4):
            try:
                time.sleep(1.5)  # Rate limiting
                resp = requests.post(self.api_url, json=payload, timeout=10)
                if resp.status_code == 200:
                    logger.info(f"Telegram: sent message ({len(text)} chars)")
                    return
                elif resp.status_code == 429:
                    try:
                        retry_after = resp.json().get("parameters", {}).get("retry_after", 30)
                    except (ValueError, KeyError):
                        retry_after = 30
                    logger.warning(
                        f"Telegram: rate limited, waiting {retry_after}s (attempt {attempt}/3)"
                    )
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
