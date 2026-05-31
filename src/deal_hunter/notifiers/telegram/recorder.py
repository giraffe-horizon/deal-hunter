"""Fire-and-forget recorder for successful Telegram sends.

`TelegramNotifier.send_*` methods call this after a 200 response from the
Telegram API. The recorder builds its own short-lived session via
`get_session` (the project's existing context manager) so that HTTP I/O
stays decoupled from the per-hunt transactional boundary.

A DB error here MUST NOT bubble up. A successful Telegram message that
fails to record is still a successful message; we log at WARNING and
move on.
"""

from __future__ import annotations

import json
import logging

from sqlalchemy.exc import SQLAlchemyError

from deal_hunter.storage.database import get_session
from deal_hunter.storage.repositories import SentNotificationRepository

logger = logging.getLogger(__name__)


def record_sent_notification(
    *,
    alert_type: str,
    payload: dict,
    deal_id: str | None = None,
    profile: str | None = None,
) -> None:
    """Insert one row into sent_notifications. Errors are logged, never raised."""
    try:
        with get_session() as session:
            SentNotificationRepository(session).record(
                alert_type=alert_type,
                payload_json=json.dumps(payload),
                deal_id=deal_id,
                profile=profile,
            )
    except SQLAlchemyError as exc:
        logger.warning("sent_notifications insert failed: %s", exc)
    except Exception as exc:  # noqa: BLE001 — final safety net for fire-and-forget
        logger.warning("sent_notifications insert failed: %s", exc)
