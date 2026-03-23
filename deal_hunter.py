#!/usr/bin/env python3
"""
Deal Hunter — universal multi-source deal monitor.
Profiles define products, sources, scoring rules, and notification targets.
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path

import yaml
from dotenv import load_dotenv

from sources import SOURCE_REGISTRY
from filters import FILTER_REGISTRY
from filters.base import BaseFilter
from notifiers.telegram import TelegramNotifier
from notifiers.notion import NotionNotifier
from utils.validation import validate_profile

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
    """Load state with TTL cleanup. Supports both old (flat) and new (sectioned) format."""
    path = _state_path(profile_name)
    if not path.exists():
        return {"seen": {}, "prices": {}}
    try:
        with open(path, 'r') as f:
            state = json.load(f)

        # Backwards compat: old format was flat dict of id -> timestamp
        if isinstance(state, list):
            return {"seen": {item: datetime.now().isoformat() for item in state}, "prices": {}}
        if "seen" not in state:
            # Old flat format — migrate
            cutoff = (datetime.now() - timedelta(days=STATE_TTL_DAYS)).isoformat()
            seen = {k: v for k, v in state.items() if isinstance(v, str) and v > cutoff}
            return {"seen": seen, "prices": {}}

        # New format — TTL cleanup on seen
        cutoff = (datetime.now() - timedelta(days=STATE_TTL_DAYS)).isoformat()
        state["seen"] = {k: v for k, v in state.get("seen", {}).items() if v > cutoff}
        if "prices" not in state:
            state["prices"] = {}
        return state
    except (json.JSONDecodeError, ValueError):
        logger.warning(f"State file corrupted for {profile_name}, resetting")
        return {"seen": {}, "prices": {}}


def save_state(profile_name: str, state: dict):
    """Save state."""
    path = _state_path(profile_name)
    try:
        with open(path, 'w') as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving state for {profile_name}: {e}")


# ──────────────── PRICE TRACKING ────────────────

def _normalize_title(title: str) -> str:
    """Normalize title for dedup and price tracking: lowercase, strip, alphanumeric only."""
    text = title.lower().strip()
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def check_price_changes(deal, state: dict, profile_name: str) -> list[str]:
    """Check if price dropped for a known deal. Returns extra plus reasons."""
    if deal.price <= 0:
        return []

    prices = state.get("prices", {})
    dedup_key = f"{_normalize_title(deal.title)}|{deal.source}"
    now = datetime.now().isoformat()

    history = prices.get(dedup_key, [])

    if not history:
        # First time seeing this deal — record price
        prices[dedup_key] = [{"price": deal.price, "ts": now}]
        state["prices"] = prices
        return []

    last_price = history[-1]["price"]
    if deal.price == last_price:
        return []

    # Price changed — append
    history.append({"price": deal.price, "ts": now})
    prices[dedup_key] = history[-10:]  # Keep last 10 entries
    state["prices"] = prices

    if deal.price < last_price:
        drop_abs = last_price - deal.price
        drop_pct = (drop_abs / last_price) * 100 if last_price > 0 else 0

        if drop_pct > 10 or drop_abs > 50:
            reason = f"+{drop_abs} PLN spadek ceny! ({last_price} → {deal.price})"
            logger.info(f"Price drop detected for '{deal.title[:60]}': {reason}")
            return [reason]
    else:
        logger.info(f"Price increased for '{deal.title[:60]}': {last_price} → {deal.price}")

    return []


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
    """Deduplicate deals by ID, then by normalized title+price with fuzzy matching."""
    seen_ids = set()
    unique = []
    seen_keys = []  # list of (normalized_title[:60], price) for fuzzy matching

    for d in deals:
        if d.id in seen_ids:
            continue
        seen_ids.add(d.id)

        norm_title = _normalize_title(d.title)[:60]
        dedup_key = (norm_title, d.price)

        # Exact match
        is_dup = False
        for existing_key in seen_keys:
            if existing_key == dedup_key:
                is_dup = True
                break
            # Fuzzy match: same price + similar title
            if existing_key[1] == d.price and d.price > 0:
                ratio = SequenceMatcher(None, existing_key[0], norm_title).ratio()
                if ratio > 0.7:
                    is_dup = True
                    break

        if is_dup:
            continue

        seen_keys.append(dedup_key)
        unique.append(d)

    return unique


# ──────────────── RUN MODES ────────────────

def run_profile(profile_name: str, verify: bool = False, validate_only: bool = False):
    """Run a single profile."""
    profile = load_profile(profile_name)

    # Validate profile
    errors = validate_profile(profile)
    if errors:
        for err in errors:
            logger.error(f"Profile '{profile_name}' validation: {err}")
        if validate_only:
            print(f"❌ Profile '{profile_name}' has {len(errors)} error(s):")
            for err in errors:
                print(f"  - {err}")
            return
        logger.error(f"Profile '{profile_name}' has validation errors, skipping")
        return

    if validate_only:
        print(f"✅ Profile '{profile_name}' is valid")
        return

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
    seen = state.get("seen", {})
    now = datetime.now().isoformat()
    emoji = profile.get("emoji", "🔍")
    currency = profile.get("currency", "PLN")
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
        if deal.id in seen:
            continue

        seen[deal.id] = now

        result = deal_filter.score_deal(deal)

        if result.rejected:
            logger.debug(f"Rejected: {deal.title[:60]} ({result.reject_reason})")
            continue

        # Price drop detection
        price_plus = check_price_changes(deal, state, profile_name)

        if result.score >= threshold:
            alert_plus = list(result.plus) + price_plus
            alerts.append({
                "deal": deal,
                "score": result.score,
                "plus": alert_plus,
                "minus": result.minus,
            })

    state["seen"] = seen
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
            notion.save_deal(a['deal'], a['score'], a['plus'], notion_db,
                             profile_name, profile=profile)

    # Telegram — top alerts individually, rest in summary
    if telegram:
        top_alerts = alerts[:max_alerts]
        remaining = alerts[max_alerts:]

        for a in top_alerts:
            tier = f"🔥🔥🔥 GORĄCA PEREŁKA" if a['score'] >= threshold_alert else f"🔥 ZNALAZŁEM OKAZJĘ"
            telegram.send_alert(
                a['deal'], a['score'], tier, a['plus'], a['minus'],
                topic_id=tg_topic, emoji=emoji, currency=currency
            )

        if remaining:
            telegram.send_summary(remaining, topic_id=tg_topic, emoji=emoji,
                                  currency=currency)

    # Console output
    for a in alerts:
        d = a['deal']
        tier = "🔥🔥🔥 PEREŁKA" if a['score'] >= threshold_alert else "🔥 OKAZJA"
        price_str = f"{d.price:,} {currency}".replace(',', ' ') if d.price > 0 else "brak ceny"
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
    currency = profile.get("currency", "PLN")
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
        price_str = f"{deal.price:,} {currency}".replace(',', ' ') if deal.price > 0 else "brak ceny"
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
    parser.add_argument("--validate", action="store_true", help="Validate profile without running")

    args = parser.parse_args()

    if args.list:
        profiles = list_profiles()
        print("Available profiles:")
        for p in profiles:
            prof = load_profile(p)
            print(f"  {prof.get('emoji', '🔍')} {p}")
        return

    if args.validate:
        if args.profile:
            run_profile(args.profile, validate_only=True)
        elif args.all:
            for profile_name in list_profiles():
                run_profile(profile_name, validate_only=True)
        else:
            print("Usage: --validate requires --profile or --all")
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
