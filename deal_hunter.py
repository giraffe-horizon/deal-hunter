#!/usr/bin/env python3
"""
Deal Hunter — universal multi-source deal monitor.
Profiles define products, sources, scoring rules, and notification targets.
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import yaml
from dotenv import load_dotenv

from sources import SOURCE_REGISTRY
from filters import FILTER_REGISTRY
from filters.base import BaseFilter
from notifiers.telegram import TelegramNotifier
from notifiers.notion import NotionNotifier

# ──────────────── SETUP ────────────────

BASE_DIR = Path(__file__).parent
PROFILES_DIR = BASE_DIR / "profiles"
STATE_DIR = BASE_DIR / "state"
STATE_TTL_DAYS = 14

load_dotenv(BASE_DIR / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(BASE_DIR / "deal_hunter.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger("deal_hunter")


# ──────────────── STATE ────────────────

def _state_path(profile_name: str) -> Path:
    STATE_DIR.mkdir(exist_ok=True)
    return STATE_DIR / f"{profile_name}_state.json"


def load_state(profile_name: str) -> dict:
    """Load state with TTL cleanup."""
    path = _state_path(profile_name)
    if not path.exists():
        return {}
    try:
        with open(path, 'r') as f:
            state = json.load(f)
        if isinstance(state, list):
            return {item: datetime.now().isoformat() for item in state}
        cutoff = (datetime.now() - timedelta(days=STATE_TTL_DAYS)).isoformat()
        return {k: v for k, v in state.items() if v > cutoff}
    except (json.JSONDecodeError, ValueError):
        logger.warning(f"State file corrupted for {profile_name}, resetting")
        return {}


def save_state(profile_name: str, state: dict):
    """Save state."""
    path = _state_path(profile_name)
    try:
        with open(path, 'w') as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving state for {profile_name}: {e}")


# ──────────────── PROFILE ────────────────

def load_profile(name: str) -> dict:
    """Load a YAML profile by name."""
    path = PROFILES_DIR / f"{name}.yaml"
    if not path.exists():
        logger.error(f"Profile not found: {path}")
        sys.exit(1)
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def list_profiles() -> list[str]:
    """List all available profile names."""
    return [p.stem for p in PROFILES_DIR.glob("*.yaml")]


def get_filter(profile: dict) -> BaseFilter:
    """Get the appropriate filter for a profile."""
    custom_filter = profile.get("custom_filter")
    if custom_filter and custom_filter in FILTER_REGISTRY:
        return FILTER_REGISTRY[custom_filter](profile)
    return BaseFilter(profile)


# ──────────────── FETCH ────────────────

def fetch_all_deals(profile: dict) -> list:
    """Fetch deals from all configured sources."""
    sources_config = profile.get("sources", {})
    all_deals = []

    for source_name, source_config in sources_config.items():
        source_class = SOURCE_REGISTRY.get(source_name)
        if not source_class:
            logger.warning(f"Unknown source: {source_name}")
            continue

        try:
            source = source_class()
            deals = source.fetch_deals(source_config)
            all_deals.extend(deals)
            logger.info(f"Source {source_name}: {len(deals)} deals fetched")
        except Exception as e:
            logger.error(f"Source {source_name} failed: {e}", exc_info=True)
            # Graceful degradation — continue with other sources

    return all_deals


def deduplicate(deals: list) -> list:
    """Deduplicate deals by ID, then by title+price similarity."""
    seen_ids = set()
    seen_titles = set()
    unique = []

    for d in deals:
        if d.id in seen_ids:
            continue
        seen_ids.add(d.id)

        # Cross-source dedup by title+price
        dedup_key = (d.title.lower().strip()[:80], d.price)
        if dedup_key in seen_titles:
            continue
        seen_titles.add(dedup_key)

        unique.append(d)

    return unique


# ──────────────── RUN MODES ────────────────

def run_profile(profile_name: str, verify: bool = False):
    """Run a single profile."""
    profile = load_profile(profile_name)
    emoji = profile.get("emoji", "🔍")
    logger.info(f"{'='*60}")
    logger.info(f"Running profile: {profile_name} {emoji} (verify={verify})")

    # Fetch
    all_deals = fetch_all_deals(profile)
    unique_deals = deduplicate(all_deals)
    logger.info(f"Total unique deals: {len(unique_deals)}")

    # Get filter
    deal_filter = get_filter(profile)

    if verify:
        _run_verify(unique_deals, deal_filter, profile)
        return

    # Normal mode
    _run_normal(unique_deals, deal_filter, profile, profile_name)


def _run_normal(deals: list, deal_filter: BaseFilter, profile: dict, profile_name: str):
    """Normal mode — find new deals, notify."""
    state = load_state(profile_name)
    now = datetime.now().isoformat()
    emoji = profile.get("emoji", "🔍")
    threshold = profile.get("score_threshold", 50)
    threshold_alert = profile.get("score_threshold_alert", 100)

    # Setup notifiers
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    tg_config = profile.get("telegram", {})
    tg_topic = tg_config.get("topic_id")
    max_alerts = tg_config.get("max_alerts", 5)

    telegram = TelegramNotifier(tg_token, tg_chat) if tg_token and tg_chat else None

    notion_config = profile.get("notion")
    notion_db = notion_config.get("database_id") if isinstance(notion_config, dict) else None
    notion_key_path = os.environ.get("NOTION_API_KEY_PATH", "~/.config/notion/api_key")
    notion = NotionNotifier(notion_key_path) if notion_db else None

    alerts = []

    for deal in deals:
        if deal.id in state:
            continue

        state[deal.id] = now

        result = deal_filter.score_deal(deal)

        if result.rejected:
            logger.debug(f"Rejected: {deal.title[:60]} ({result.reject_reason})")
            continue

        if result.score >= threshold:
            alerts.append({
                "deal": deal,
                "score": result.score,
                "plus": result.plus,
                "minus": result.minus,
            })

    save_state(profile_name, state)

    if not alerts:
        print(f"{emoji} Brak nowych okazji dla profilu {profile_name}.")
        logger.info(f"No new alerts for {profile_name}")
        return

    # Sort by score descending
    alerts.sort(key=lambda x: x['score'], reverse=True)

    # Notion — save all
    if notion and notion_db:
        for a in alerts:
            notion.save_deal(a['deal'], a['score'], a['plus'], notion_db, profile_name)

    # Telegram — top alerts individually, rest in summary
    if telegram:
        top_alerts = alerts[:max_alerts]
        remaining = alerts[max_alerts:]

        for a in top_alerts:
            tier = f"🔥🔥🔥 GORĄCA PEREŁKA" if a['score'] >= threshold_alert else f"🔥 ZNALAZŁEM OKAZJĘ"
            telegram.send_alert(
                a['deal'], a['score'], tier, a['plus'], a['minus'],
                topic_id=tg_topic, emoji=emoji
            )

        if remaining:
            telegram.send_summary(remaining, topic_id=tg_topic, emoji=emoji)

    # Console output
    for a in alerts:
        d = a['deal']
        tier = "🔥🔥🔥 PEREŁKA" if a['score'] >= threshold_alert else "🔥 OKAZJA"
        price_str = f"{d.price:,} PLN".replace(',', ' ') if d.price > 0 else "brak ceny"
        print(f"{emoji} {tier} (score: {a['score']})")
        print(f"  {d.title}")
        print(f"  Cena: {price_str} | Źródło: {d.source}")
        if a['plus']:
            print(f"  ✅ {', '.join(a['plus'][:6])}")
        if a['minus']:
            print(f"  ⚠️  {', '.join(a['minus'][:4])}")
        print(f"  LINK: {d.link}")
        print()

    logger.info(f"Profile {profile_name}: {len(alerts)} alerts")


def _run_verify(deals: list, deal_filter: BaseFilter, profile: dict):
    """Verify mode — analyze all deals without state tracking."""
    emoji = profile.get("emoji", "🔍")
    threshold = profile.get("score_threshold", 50)
    threshold_alert = profile.get("score_threshold_alert", 100)
    profile_name = profile.get("name", "unknown")

    print(f"\n{'='*60}")
    print(f"  {emoji} ANALIZA OFERT — {profile_name.upper()} — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Znaleziono {len(deals)} ofert")
    print(f"{'='*60}\n")

    scored = []
    rejected = 0

    for deal in deals:
        result = deal_filter.score_deal(deal)
        if result.rejected:
            rejected += 1
            continue
        scored.append((deal, result))

    if rejected:
        print(f"  (Odrzucono {rejected} ofert)\n")

    scored.sort(key=lambda x: x[1].score, reverse=True)

    for deal, result in scored:
        price_str = f"{deal.price:,} PLN".replace(',', ' ') if deal.price > 0 else "brak ceny"
        temp_str = f" | temp: {deal.temperature}°" if deal.temperature else ""

        if result.score >= threshold_alert:
            status = "🔥🔥🔥 PEREŁKA"
        elif result.score >= threshold:
            status = "🔥 POTENCJAŁ"
        elif result.score >= 20:
            status = "🤔 MOŻE"
        else:
            status = "❌ NIE PASUJE"

        print(f"[{status}] Score: {result.score}")
        print(f"  {deal.title}")
        print(f"  Cena: {price_str}{temp_str} | Źródło: {deal.source}")
        if result.plus:
            print(f"  ✅ {', '.join(result.plus[:6])}")
        if result.minus:
            print(f"  ⚠️  {', '.join(result.minus[:4])}")
        print(f"  {deal.link}")
        print()


# ──────────────── CLI ────────────────

def main():
    parser = argparse.ArgumentParser(description="Deal Hunter — multi-source deal monitor")
    parser.add_argument("--profile", "-p", type=str, help="Profile name to run")
    parser.add_argument("--all", "-a", action="store_true", help="Run all profiles")
    parser.add_argument("--verify", "-v", action="store_true", help="Verify mode (show all, no state)")
    parser.add_argument("--list", "-l", action="store_true", help="List available profiles")

    args = parser.parse_args()

    if args.list:
        profiles = list_profiles()
        print("Available profiles:")
        for p in profiles:
            prof = load_profile(p)
            print(f"  {prof.get('emoji', '🔍')} {p}")
        return

    if args.all:
        for profile_name in list_profiles():
            try:
                run_profile(profile_name, verify=args.verify)
            except Exception as e:
                logger.error(f"Profile {profile_name} failed: {e}", exc_info=True)
        return

    if args.profile:
        run_profile(args.profile, verify=args.verify)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
