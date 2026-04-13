#!/usr/bin/env python3
"""Migrate existing state/*.json files into SQLite database.

Idempotent — safe to run multiple times. Existing records are updated,
not duplicated.

Usage:
    python scripts/migrate_state_to_sqlite.py
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from storage.sqlite import SQLiteStorage

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent
STATE_DIR = BASE_DIR / "state"
DB_PATH = STATE_DIR / "deals.db"


def migrate_state_file(db: SQLiteStorage, state_path: Path) -> dict:
    """Migrate a single state JSON file. Returns stats dict."""
    profile_name = state_path.stem.replace("_state", "")
    stats = {"profile": profile_name, "seen": 0, "prices": 0}

    try:
        with state_path.open() as f:
            state = json.load(f)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Skipping corrupted state file {state_path.name}: {e}")
        return stats

    # Handle old flat format
    if isinstance(state, list):
        logger.info(f"  {state_path.name}: old list format, skipping (no deal data)")
        return stats

    seen = state.get("seen", {})
    prices = state.get("prices", {})

    # Migrate seen deals — we only have ID and timestamp, no full deal data
    now = datetime.now().isoformat()
    for deal_id, first_seen_ts in seen.items():
        source = deal_id.split(":")[0] if ":" in deal_id else "unknown"
        db.import_legacy_deal(
            deal_id=deal_id,
            title=f"[migrated] {deal_id}",
            price=0,
            source=source,
            profile=profile_name,
            first_seen=first_seen_ts,
            last_seen=first_seen_ts,
        )
        stats["seen"] += 1

    # Migrate price history
    for price_key, history in prices.items():
        # price_key format: "normalized_title|source"
        # We don't have original deal IDs, so create a synthetic one
        parts = price_key.rsplit("|", 1)
        source = parts[1] if len(parts) > 1 else "unknown"
        synthetic_id = f"{source}:migrated:{hash(price_key) % 10**8}"

        # Ensure the deal record exists
        db.import_legacy_deal(
            deal_id=synthetic_id,
            title=f"[migrated] {parts[0][:100]}",
            price=history[-1]["price"] if history else 0,
            source=source,
            profile=profile_name,
            first_seen=history[0]["ts"] if history else now,
            last_seen=history[-1]["ts"] if history else now,
        )

        for entry in history:
            db.import_legacy_price(synthetic_id, entry["price"], entry["ts"])
            stats["prices"] += 1

    db.commit()
    return stats


def main() -> None:
    if not STATE_DIR.exists():
        logger.info("No state directory found, nothing to migrate.")
        return

    state_files = list(STATE_DIR.glob("*_state.json"))
    if not state_files:
        logger.info("No state files found, nothing to migrate.")
        return

    logger.info(f"Found {len(state_files)} state file(s) to migrate")
    logger.info(f"Database: {DB_PATH}")

    with SQLiteStorage(DB_PATH) as db:
        total_seen = 0
        total_prices = 0

        for state_path in state_files:
            logger.info(f"Migrating {state_path.name}...")
            stats = migrate_state_file(db, state_path)
            total_seen += stats["seen"]
            total_prices += stats["prices"]
            logger.info(
                f"  {stats['profile']}: {stats['seen']} deals, {stats['prices']} price entries"
            )

    logger.info(f"Migration complete: {total_seen} deals, {total_prices} price entries")


if __name__ == "__main__":
    main()
