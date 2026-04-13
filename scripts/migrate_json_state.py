#!/usr/bin/env python3
"""One-time migration: import state/*.json seen-deals and prices into SQLite.

Usage:
    python scripts/migrate_json_state.py [--dry-run]

Reads state/*_state.json files, imports:
- "seen" entries -> seen_deals table
- "prices" entries -> price_history table (dedup against existing)

Safe to run multiple times (idempotent via INSERT OR IGNORE).
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text  # noqa: E402

from storage.database import (
    engine,  # noqa: E402
    get_session,  # noqa: E402
)
from storage.models import Base, SeenDeal  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

STATE_DIR = Path(__file__).parent.parent / "state"


def migrate_file(path: Path, session, dry_run: bool = False) -> dict:
    """Migrate a single state JSON file. Returns counts."""
    profile = path.stem.replace("_state", "")
    counts = {"seen": 0, "prices": 0, "skipped": 0}

    try:
        with path.open(encoding="utf-8") as f:
            state = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Skipping {path.name}: {e}")
        return counts

    # Handle legacy formats
    if isinstance(state, list):
        state = {"seen": {item: datetime.now().isoformat() for item in state}, "prices": {}}
    if "seen" not in state:
        state = {"seen": {k: v for k, v in state.items() if isinstance(v, str)}, "prices": {}}

    # Migrate seen entries
    for deal_id, timestamp in state.get("seen", {}).items():
        if dry_run:
            counts["seen"] += 1
            continue
        # Check if already migrated
        exists = session.query(SeenDeal).filter_by(deal_id=deal_id, profile=profile).first()
        if exists:
            counts["skipped"] += 1
            continue
        session.add(
            SeenDeal(
                deal_id=deal_id,
                profile=profile,
                dedup_key=deal_id,  # best available dedup key from legacy data
                first_seen_at=timestamp,
            )
        )
        counts["seen"] += 1

    # Migrate price history
    for deal_id, entries in state.get("prices", {}).items():
        for entry in entries:
            price = entry.get("price", 0)
            ts = entry.get("ts", "")
            if not price or not ts:
                continue
            if dry_run:
                counts["prices"] += 1
                continue
            session.execute(
                text(
                    "INSERT OR IGNORE INTO price_points (deal_id, price, recorded_at)"
                    " VALUES (:deal_id, :price, :ts)"
                ),
                {"deal_id": deal_id, "price": price, "ts": ts},
            )
            counts["prices"] += 1

    return counts


def main() -> None:
    dry_run = "--dry-run" in sys.argv

    # Ensure seen_deals table exists
    Base.metadata.create_all(engine)

    json_files = sorted(STATE_DIR.glob("*_state.json"))
    if not json_files:
        logger.info("No state JSON files found in %s", STATE_DIR)
        return

    logger.info(
        "%s %d state files from %s",
        "DRY RUN:" if dry_run else "Migrating",
        len(json_files),
        STATE_DIR,
    )

    total = {"seen": 0, "prices": 0, "skipped": 0}
    with get_session() as session:
        for path in json_files:
            counts = migrate_file(path, session, dry_run=dry_run)
            logger.info(
                "  %s: %d seen, %d prices, %d skipped",
                path.name,
                counts["seen"],
                counts["prices"],
                counts["skipped"],
            )
            for k in total:
                total[k] += counts[k]

    logger.info(
        "Total: %d seen entries, %d price entries, %d skipped",
        total["seen"],
        total["prices"],
        total["skipped"],
    )
    if not dry_run:
        logger.info("Migration complete. State JSON files can be removed (keep health.json).")


if __name__ == "__main__":
    main()
