"""Pure decision logic — should a price-drop alert be sent right now?

Called by AlertService.send_price_drop_alerts before quiet-hours queuing.
A suppressed alert is dropped entirely (not queued for later).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from deal_hunter.core.notification_config import NotificationConfig
    from deal_hunter.storage.repositories import (
        OfferRepository,
        SentNotificationRepository,
    )


def should_send_price_drop(
    *,
    deal_id: str,
    profile_name: str,  # noqa: ARG001 — reserved for per-profile log filtering.
    is_all_time_low: bool,
    config: NotificationConfig,
    deal_repo: OfferRepository,
    sent_repo: SentNotificationRepository,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """Returns (allow, reason). reason is for logging."""
    now = now or datetime.now()

    offer = deal_repo.get_by_id(deal_id)
    muted_until = (offer or {}).get("muted_until")
    # ISO-string compare works because lexical order matches chronological for ISO 8601.
    if muted_until and muted_until > now.isoformat():
        return False, f"muted_until={muted_until}"

    if config.cooldown_days <= 0:
        return True, "ok"

    last_sent = sent_repo.last_sent_at(deal_id, "price_drop")
    if not last_sent:
        return True, "ok"

    try:
        last_sent_dt = datetime.fromisoformat(last_sent)
    except ValueError:
        return True, "ok"

    cooldown_expires = last_sent_dt + timedelta(days=config.cooldown_days)
    if now >= cooldown_expires:
        return True, "ok"

    if is_all_time_low and config.alert_through_cooldown_if_ath_low:
        return True, "ath_override"

    remaining = cooldown_expires - now
    days_remaining = max(1, int(remaining.total_seconds() // 86400))
    return False, f"cooldown:{days_remaining}d_remaining"
