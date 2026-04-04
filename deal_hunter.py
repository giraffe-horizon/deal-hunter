#!/usr/bin/env python3
"""Deal Hunter — universal multi-source deal monitor.

Profiles define products, sources, scoring rules, and notification targets.
"""

import argparse
import importlib.metadata
import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path

import yaml
from dotenv import load_dotenv

from filters import FILTER_REGISTRY
from storage.sqlite import SQLiteStorage

__version__ = "0.1.0"  # maintained by semantic-release
try:
    __version__ = importlib.metadata.version("deal-hunter")
except importlib.metadata.PackageNotFoundError:
    pass  # use the version above when not installed as package
from filters.base import BaseFilter
from notifiers.telegram import TelegramNotifier
from sources import SOURCE_REGISTRY
from utils.validation import validate_profile

# ──────────────── SETUP ────────────────

BASE_DIR = Path(__file__).parent
PROFILES_DIR = BASE_DIR / "profiles"
STATE_DIR = BASE_DIR / "state"
STATE_TTL_DAYS = 14
DB_PATH = STATE_DIR / "deals.db"

load_dotenv(BASE_DIR / ".env")


def _setup_logging() -> None:
    """Configure logging once on the root logger. Child loggers just propagate."""
    root = logging.getLogger()
    if root.handlers:
        return  # Already configured — avoid duplicate handlers
    root.setLevel(logging.INFO)
    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)
    fh = logging.FileHandler(BASE_DIR / "deal_hunter.log", encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)


_setup_logging()
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
        with open(path) as f:
            state = json.load(f)

        # Backwards compat: old format was flat list
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
        return dict(state)
    except (json.JSONDecodeError, ValueError):
        logger.warning(f"State file corrupted for {profile_name}, resetting")
        return {"seen": {}, "prices": {}}


def save_state(profile_name: str, state: dict) -> None:
    """Save state to disk."""
    path = _state_path(profile_name)
    try:
        with open(path, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving state for {profile_name}: {e}")


# ──────────────── PRICE TRACKING ────────────────


def _normalize_title(title: str) -> str:
    """Normalize title for dedup and price tracking: lowercase, strip, alphanumeric only."""
    text = title.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
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
            reason = f"price drop {drop_abs} PLN ({last_price} -> {deal.price})"
            logger.info(f"Price drop detected for '{deal.title[:60]}': {reason}")
            return [reason]
    else:
        logger.info(f"Price increased for '{deal.title[:60]}': {last_price} -> {deal.price}")

    return []


# ──────────────── PROFILE ────────────────


EXAMPLES_DIR = BASE_DIR / "examples"


def load_profile(name: str) -> dict:
    """Load a YAML profile by name. Checks profiles/ first, then examples/."""
    path = PROFILES_DIR / f"{name}.yaml"
    if not path.exists():
        path = EXAMPLES_DIR / f"{name}.yaml"
    if not path.exists():
        logger.error(f"Profile not found: {name}")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return dict(yaml.safe_load(f))


def list_profiles(include_disabled: bool = True) -> list[str]:
    """List available profile names. Checks profiles/ and examples/."""
    names: list[str] = []
    for directory in (PROFILES_DIR, EXAMPLES_DIR):
        if not directory.exists():
            continue
        for p in directory.glob("*.yaml"):
            if p.stem in names:
                continue
            if not include_disabled:
                with open(p, encoding="utf-8") as f:
                    prof = yaml.safe_load(f)
                if isinstance(prof, dict) and not prof.get("enabled", True):
                    continue
            names.append(p.stem)
    return names


def get_filter(profile: dict) -> BaseFilter:
    """Get the appropriate filter for a profile."""
    custom_filter = profile.get("custom_filter")
    if custom_filter and custom_filter in FILTER_REGISTRY:
        return FILTER_REGISTRY[custom_filter](profile)
    return BaseFilter(profile)


def _detect_category(deal, profile: dict, profile_name: str = "") -> str:
    """Detect product category from deal title+description using profile's categories mapping."""
    categories = profile.get("categories", {})
    if not categories:
        return profile_name if profile_name else ""

    text = (deal.title + " " + deal.description).lower()
    for category, keywords in categories.items():
        if any(kw.lower() in text for kw in keywords):
            return str(category)
    return profile_name if profile_name else ""


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
    seen_ids: set[str] = set()
    unique: list = []
    seen_keys: list[tuple[str, int]] = []

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


def run_profile(profile_name: str, verify: bool = False, validate_only: bool = False) -> None:
    """Run a single profile."""
    profile = load_profile(profile_name)

    # Validate profile
    errors = validate_profile(profile)
    if errors:
        for err in errors:
            logger.error(f"Profile '{profile_name}' validation: {err}")
        if validate_only:
            print(f"\u274c Profile '{profile_name}' has {len(errors)} error(s):")
            for err in errors:
                print(f"  - {err}")
            return
        logger.error(f"Profile '{profile_name}' has validation errors, skipping")
        return

    if validate_only:
        print(f"\u2705 Profile '{profile_name}' is valid")
        return

    emoji = profile.get("emoji", "\U0001f50d")
    logger.info(f"{'=' * 60}")
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


def _run_normal(deals: list, deal_filter: BaseFilter, profile: dict, profile_name: str) -> None:
    """Normal mode — find new deals, score, and notify."""
    state = load_state(profile_name)
    seen = state.get("seen", {})
    now = datetime.now().isoformat()
    emoji = profile.get("emoji", "\U0001f50d")
    currency = profile.get("currency", "PLN")
    threshold = profile.get("score_threshold", 50)
    threshold_alert = profile.get("score_threshold_alert", 100)

    # Setup notifiers
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not tg_token or not tg_chat:
        logger.warning("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set — Telegram alerts disabled")
    tg_config = profile.get("telegram", {})
    tg_topic = tg_config.get("topic_id")
    max_alerts = tg_config.get("max_alerts", 5)

    telegram = TelegramNotifier(tg_token, tg_chat) if tg_token and tg_chat else None

    # SQLite persistence
    db: SQLiteStorage | None = None
    try:
        db = SQLiteStorage(DB_PATH)
    except Exception as e:
        logger.error(f"SQLite storage unavailable, continuing without persistence: {e}")

    alerts: list[dict] = []

    try:
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

            # Persist to SQLite
            if db and result.score >= threshold:
                category = _detect_category(deal, profile, profile_name)
                db.upsert_deal(deal, profile_name, result.score, category)

            if result.score >= threshold:
                alert_plus = list(result.plus) + price_plus
                alerts.append(
                    {
                        "deal": deal,
                        "score": result.score,
                        "plus": alert_plus,
                        "minus": result.minus,
                    }
                )
    finally:
        if db:
            db.close()

    state["seen"] = seen
    save_state(profile_name, state)

    if not alerts:
        print(f"{emoji} No new deals for profile {profile_name}.")
        logger.info(f"No new alerts for {profile_name}")
        return

    # Sort by score descending
    alerts.sort(key=lambda x: x["score"], reverse=True)

    # Telegram — top alerts individually, rest in summary
    if telegram:
        top_alerts = alerts[:max_alerts]
        remaining = alerts[max_alerts:]

        for a in top_alerts:
            tier = (
                "\U0001f525\U0001f525\U0001f525 GOR\u0104CA PERE\u0141KA"
                if a["score"] >= threshold_alert
                else "\U0001f525 ZNALAZ\u0141EM OKAZJ\u0118"
            )
            telegram.send_alert(
                a["deal"],
                a["score"],
                tier,
                a["plus"],
                a["minus"],
                topic_id=tg_topic,
                emoji=emoji,
                currency=currency,
            )

        if remaining:
            telegram.send_summary(remaining, topic_id=tg_topic, emoji=emoji, currency=currency)

    # Console output
    for a in alerts:
        d = a["deal"]
        tier = (
            "\U0001f525\U0001f525\U0001f525 TOP DEAL"
            if a["score"] >= threshold_alert
            else "\U0001f525 DEAL"
        )
        price_str = f"{d.price:,} {currency}".replace(",", " ") if d.price > 0 else "no price"
        print(f"{emoji} {tier} (score: {a['score']})")
        print(f"  {d.title}")
        print(f"  Price: {price_str} | Source: {d.source}")
        if a["plus"]:
            print(f"  \u2705 {', '.join(a['plus'][:6])}")
        if a["minus"]:
            print(f"  \u26a0\ufe0f  {', '.join(a['minus'][:4])}")
        print(f"  LINK: {d.link}")
        print()

    logger.info(f"Profile {profile_name}: {len(alerts)} alerts")


def _run_verify(deals: list, deal_filter: BaseFilter, profile: dict) -> None:
    """Verify mode — analyze all deals without state tracking."""
    emoji = profile.get("emoji", "\U0001f50d")
    currency = profile.get("currency", "PLN")
    threshold = profile.get("score_threshold", 50)
    threshold_alert = profile.get("score_threshold_alert", 100)
    profile_name = profile.get("name", "unknown")

    print(f"\n{'=' * 60}")
    print(
        f"  {emoji} DEAL ANALYSIS \u2014 {profile_name.upper()} \u2014 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    print(f"  Found {len(deals)} deals")
    print(f"{'=' * 60}\n")

    scored: list[tuple] = []
    rejected = 0

    for deal in deals:
        result = deal_filter.score_deal(deal)
        if result.rejected:
            rejected += 1
            continue
        scored.append((deal, result))

    if rejected:
        print(f"  ({rejected} deals rejected)\n")

    scored.sort(key=lambda x: x[1].score, reverse=True)

    for deal, result in scored:
        price_str = f"{deal.price:,} {currency}".replace(",", " ") if deal.price > 0 else "no price"
        temp_str = f" | temp: {deal.temperature}\u00b0" if deal.temperature else ""

        if result.score >= threshold_alert:
            status = "\U0001f525\U0001f525\U0001f525 TOP DEAL"
        elif result.score >= threshold:
            status = "\U0001f525 POTENTIAL"
        elif result.score >= 20:
            status = "\U0001f914 MAYBE"
        else:
            status = "\u274c NO MATCH"

        print(f"[{status}] Score: {result.score}")
        print(f"  {deal.title}")
        print(f"  Price: {price_str}{temp_str} | Source: {deal.source}")
        if result.plus:
            print(f"  \u2705 {', '.join(result.plus[:6])}")
        if result.minus:
            print(f"  \u26a0\ufe0f  {', '.join(result.minus[:4])}")
        print(f"  {deal.link}")
        print()


# ──────────────── CLI ────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Deal Hunter \u2014 multi-source deal monitor")
    parser.add_argument("--profile", "-p", type=str, help="Profile name to run")
    parser.add_argument("--all", "-a", action="store_true", help="Run all profiles")
    parser.add_argument(
        "--verify",
        "-v",
        action="store_true",
        help="Verify mode (show all deals with scores, no state)",
    )
    parser.add_argument("--list", "-l", action="store_true", help="List available profiles")
    parser.add_argument("--validate", action="store_true", help="Validate profile without running")
    parser.add_argument("--init", action="store_true", help="Create a new profile interactively")
    parser.add_argument("--version", action="version", version=f"Deal Hunter {__version__}")

    args = parser.parse_args()

    if args.init:
        from utils.init_profile import run_init

        run_init()
        return

    if args.list:
        profiles = list_profiles()
        print("Available profiles:")
        for p in profiles:
            prof = load_profile(p)
            print(f"  {prof.get('emoji', '\U0001f50d')} {p}")
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
        for profile_name in list_profiles(include_disabled=False):
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
