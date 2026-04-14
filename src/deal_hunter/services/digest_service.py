"""Weekly price-drop digest: aggregate SQLite price_points + send to Telegram."""

from __future__ import annotations

import logging

from deal_hunter.core.settings import get_settings
from deal_hunter.notifiers.telegram import TelegramNotifier
from deal_hunter.services.runtime import get_topic_id
from deal_hunter.storage.database import get_session
from deal_hunter.storage.repositories import PriceRepository

logger = logging.getLogger(__name__)


def run_digest() -> None:
    """Generate and send weekly price digest from SQLite price_points."""
    s = get_settings()
    if not s.telegram_configured:
        logger.warning("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set — cannot send digest")
        print(
            "Warning: Telegram not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env"
        )
        return

    with get_session() as session:
        drops = PriceRepository(session).get_drops(days=7)

    if not drops:
        print("No price drops in the last 7 days.")
        return

    # Console output
    print(f"\n{'=' * 60}")
    print(f"  \U0001f4ca WEEKLY PRICE DIGEST — {len(drops)} drops")
    print(f"{'=' * 60}\n")

    for d in drops:
        old_str = f"{d['old_price']:,} PLN".replace(",", " ")
        new_str = f"{d['new_price']:,} PLN".replace(",", " ")
        lowest = " \U0001f525" if d.get("is_lowest_ever") else ""
        title = d["title"][:60]
        pct = d["diff_percent"]
        print(f"  \U0001f4c9 {title}: {old_str} -> {new_str} (-{pct}%){lowest}")

    # Send Telegram digest
    topic_id = get_topic_id()
    telegram = TelegramNotifier(s.telegram_bot_token, s.telegram_chat_id)
    telegram.send_digest(drops, topic_id=topic_id)
    print(f"\nDigest sent to Telegram ({len(drops)} drops).")

    # Generate and send digest bar chart
    try:
        from deal_hunter.visualization.charts import generate_digest_chart

        chart_path = generate_digest_chart(drops)
        telegram.send_photo(
            str(chart_path),
            caption="\U0001f4ca Najwi\u0119ksze spadki cen (ostatni tydzie\u0144)",
            topic_id=topic_id,
        )
        print("Digest chart sent to Telegram.")
    except ImportError:
        logger.info("matplotlib not installed — skipping digest chart")
    except Exception as e:
        logger.warning(f"Failed to generate digest chart: {e}")
