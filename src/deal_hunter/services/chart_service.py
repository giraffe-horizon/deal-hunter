"""Chart services: price history chart + per-profile trend chart → Telegram."""

from __future__ import annotations

import sys

from deal_hunter.core.settings import get_settings
from deal_hunter.notifiers.telegram import TelegramNotifier
from deal_hunter.services.runtime import get_topic_id
from deal_hunter.storage.database import get_session


def run_price_chart(deal_id: str) -> None:
    """Generate a price history chart for a deal and send to Telegram."""
    from deal_hunter.visualization.charts import generate_price_chart

    with get_session() as session:
        try:
            chart_path = generate_price_chart(deal_id, session)
        except (ValueError, ImportError) as e:
            print(f"Error: {e}")
            sys.exit(1)

    print(f"Chart saved to {chart_path}")
    _send_chart(chart_path, caption=f"\U0001f4c8 Historia cen: {deal_id}")


def run_trend_chart(profile_name: str) -> None:
    """Generate a trend chart for a profile and send to Telegram."""
    from deal_hunter.visualization.charts import generate_trend_chart

    with get_session() as session:
        try:
            chart_path = generate_trend_chart(profile_name, session)
        except (ValueError, ImportError) as e:
            print(f"Error: {e}")
            sys.exit(1)

    print(f"Chart saved to {chart_path}")
    _send_chart(chart_path, caption=f"\U0001f4ca Trend cenowy: {profile_name}")


def _send_chart(chart_path: object, *, caption: str) -> None:
    """Send a chart file to Telegram if configured, else print a skip message."""
    s = get_settings()
    if not s.telegram_configured:
        print("Telegram not configured — chart not sent.")
        return
    telegram = TelegramNotifier(s.telegram_bot_token, s.telegram_chat_id)
    telegram.send_photo(str(chart_path), caption=caption, topic_id=get_topic_id())
    print("Chart sent to Telegram.")
