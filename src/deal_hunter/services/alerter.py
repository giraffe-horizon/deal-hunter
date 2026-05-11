"""Notification dispatch, quiet hours, and alert queuing."""

from __future__ import annotations

import html
import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING

from deal_hunter.core.settings import Settings

if TYPE_CHECKING:
    from deal_hunter.notifiers.telegram import TelegramNotifier
    from deal_hunter.storage.repositories import AlertQueueRepository


logger = logging.getLogger(__name__)


def is_quiet_hours(profile: dict) -> bool:
    """Check if current time is within quiet hours.

    Priority: profile quiet_hours > env QUIET_HOURS_START/END > disabled.
    """
    qh = profile.get("quiet_hours")
    if qh:
        start_str = qh.get("start")
        end_str = qh.get("end")
    else:
        # Read fresh so env changes (including test monkeypatch) are picked up.
        s = Settings()
        start_str = s.quiet_hours_start
        end_str = s.quiet_hours_end

    if not start_str or not end_str:
        return False

    try:
        start_h, start_m = map(int, start_str.split(":"))
        end_h, end_m = map(int, end_str.split(":"))
    except (ValueError, AttributeError):
        logger.warning(f"Invalid quiet hours format: {start_str}-{end_str}")
        return False

    now = datetime.now()
    current_minutes = now.hour * 60 + now.minute
    start_minutes = start_h * 60 + start_m
    end_minutes = end_h * 60 + end_m

    if start_minutes <= end_minutes:
        # Same day range (e.g., 13:00-15:00)
        return start_minutes <= current_minutes < end_minutes
    # Overnight range (e.g., 22:00-07:00)
    return current_minutes >= start_minutes or current_minutes < end_minutes


class AlertService:
    """Sends deal alerts, price drops, and digests via Telegram."""

    def __init__(
        self,
        telegram: TelegramNotifier | None,
        alert_repo: AlertQueueRepository | None = None,
    ) -> None:
        self.telegram = telegram
        self.alert_repo = alert_repo

    def flush_queued(
        self, profile_name: str, profile: dict, topic_id: int | None, max_alerts: int
    ) -> int:
        """Flush queued alerts from previous quiet hours. Returns count flushed."""
        if not self.telegram or not self.alert_repo or is_quiet_hours(profile):
            return 0

        pending = self.alert_repo.get_pending(profile=profile_name)
        if not pending:
            return 0

        flush_count = min(len(pending), max_alerts)
        for alert_data in pending[:flush_count]:
            payload = json.loads(alert_data["payload"])
            if alert_data["alert_type"] == "deal":
                self.telegram.send_text(
                    f"\U0001f514 Zakolejkowany alert:\n"
                    f"<b>{html.escape(payload.get('title', ''))}</b>\n"
                    f"\U0001f4b0 {payload.get('price', 0):,} PLN\n"
                    f"Score: {payload.get('score', 0)}\n"
                    f'\U0001f517 <a href="{html.escape(payload.get("link", ""))}">Link</a>',
                    topic_id=topic_id,
                )
            elif alert_data["alert_type"] == "price_drop":
                self.telegram.send_text(
                    f"\U0001f514 Zakolejkowany spadek ceny:\n"
                    f"<b>{html.escape(payload.get('title', ''))}</b>\n"
                    f"{payload.get('old_price', 0):,}"
                    f" \u2192 {payload.get('new_price', 0):,} PLN",
                    topic_id=topic_id,
                )
        self.alert_repo.mark_sent([p["id"] for p in pending[:flush_count]])
        logger.info(f"Flushed {flush_count} queued alerts for {profile_name}")
        return flush_count

    def send_price_drop_alerts(
        self,
        drops: list[dict],
        profile: dict,
        profile_name: str,
        topic_id: int | None,
        max_alerts: int,
    ) -> int:
        """Send or queue price drop alerts. Returns count sent/queued."""
        if not drops or not self.telegram:
            return 0

        emoji = profile.get("emoji", "\U0001f50d")
        currency = profile.get("currency", "PLN")

        drops.sort(key=lambda x: x["price_change"]["diff_percent"], reverse=True)
        count = min(len(drops), max_alerts)

        if is_quiet_hours(profile) and self.alert_repo:
            for pda in drops[:count]:
                payload = json.dumps(
                    {
                        "deal_id": pda["deal"].id,
                        "title": pda["deal"].title,
                        "link": pda["deal"].link,
                        "old_price": pda["price_change"]["old_price"],
                        "new_price": pda["price_change"]["new_price"],
                        "diff_pln": pda["price_change"]["diff_pln"],
                        "diff_percent": pda["price_change"]["diff_percent"],
                    }
                )
                self.alert_repo.queue(profile_name, "price_drop", payload, deal_id=pda["deal"].id)
            logger.info(f"Queued {count} price drop alerts (quiet hours)")
        else:
            for pda in drops[:count]:
                self.telegram.send_price_drop_alert(
                    pda["deal"],
                    pda["price_change"],
                    topic_id=topic_id,
                    emoji=emoji,
                    currency=currency,
                )
            logger.info(f"Sent {count} price drop alerts for {profile_name}")
        return count

    def send_deal_alerts(
        self,
        alerts: list[dict],
        profile: dict,
        profile_name: str,
        topic_id: int | None,
        max_alerts: int,
    ) -> int:
        """Send or queue deal alerts. Returns count sent/queued."""
        if not alerts or not self.telegram:
            return 0

        emoji = profile.get("emoji", "\U0001f50d")
        currency = profile.get("currency", "PLN")
        threshold_alert = profile.get("score_threshold_alert", 100)

        alerts.sort(key=lambda x: x["score"], reverse=True)

        if is_quiet_hours(profile) and self.alert_repo:
            count = min(len(alerts), max_alerts)
            for a in alerts[:count]:
                payload = json.dumps(
                    {
                        "deal_id": a["deal"].id,
                        "title": a["deal"].title,
                        "price": a["deal"].price,
                        "link": a["deal"].link,
                        "score": a["score"],
                        "plus": a["plus"][:6],
                        "minus": a["minus"][:4],
                    }
                )
                self.alert_repo.queue(profile_name, "deal", payload, deal_id=a["deal"].id)
            logger.info(f"Queued {count} deal alerts (quiet hours)")
            return count

        top_alerts = alerts[:max_alerts]
        remaining = alerts[max_alerts:]

        for a in top_alerts:
            tier = (
                "\U0001f525\U0001f525\U0001f525 GOR\u0104CA PERE\u0141KA"
                if a["score"] >= threshold_alert
                else "\U0001f525 ZNALAZ\u0141EM OKAZJ\u0118"
            )
            self.telegram.send_alert(
                a["deal"],
                a["score"],
                tier,
                a["plus"],
                a["minus"],
                topic_id=topic_id,
                emoji=emoji,
                currency=currency,
            )

        if remaining:
            self.telegram.send_summary(
                remaining,
                topic_id=topic_id,
                emoji=emoji,
                currency=currency,
            )

        return len(top_alerts)

    def send_source_failure_alert(
        self, failing_sources: list[str], sources_health: dict, topic_id: int | None
    ) -> None:
        """Send Telegram alert for sources with too many consecutive failures."""
        if not self.telegram:
            return

        lines = []
        for name in failing_sources:
            data = sources_health[name]
            count = data.get("consecutive_failures", 0)
            last = data.get("last_success", "never")
            lines.append(f"  \u2022 {name}: {count} consecutive failures (last success: {last})")

        msg = "\u26a0\ufe0f Deal Hunter: source failures detected!\n\n" + "\n".join(lines)
        self.telegram.send_text(msg, topic_id=topic_id)
