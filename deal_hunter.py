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
import time
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path

import yaml
from dotenv import load_dotenv

from filters import FILTER_REGISTRY
from health import (
    build_health_data,
    check_watchdog,
    get_failing_sources,
    load_health,
    print_health_status,
    save_health,
    update_sources_health,
)
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


def get_price_tracking_config(profile: dict) -> dict:
    """Get price tracking config with defaults."""
    pt = profile.get("price_tracking", {})
    return {
        "enabled": pt.get("enabled", True),
        "min_drop_percent": pt.get("min_drop_percent", 10),
        "min_drop_amount": pt.get("min_drop_amount", 100),
        "track_increases": pt.get("track_increases", False),
    }


def check_price_changes(
    deal,
    state: dict,
    profile_name: str,
    profile: dict | None = None,
    db: "SQLiteStorage | None" = None,
) -> dict | None:
    """Check if price changed for a known deal.

    Returns a structured dict on significant change:
        {type: 'drop'|'increase', old_price, new_price, diff_pln, diff_percent, is_lowest_ever}
    Returns None if no significant change.

    The state JSON price tracking always runs (backwards compat).
    If db (SQLiteStorage) is available, also checks for lowest-ever price.
    """
    if deal.price <= 0:
        return None

    pt_config = get_price_tracking_config(profile) if profile else {
        "enabled": True, "min_drop_percent": 10, "min_drop_amount": 100, "track_increases": False,
    }

    if not pt_config["enabled"]:
        return None

    prices = state.get("prices", {})
    dedup_key = f"{_normalize_title(deal.title)}|{deal.source}"
    now = datetime.now().isoformat()

    history = prices.get(dedup_key, [])

    if not history:
        # First time seeing this deal — record price
        prices[dedup_key] = [{"price": deal.price, "ts": now}]
        state["prices"] = prices
        return None

    last_price = history[-1]["price"]
    if deal.price == last_price:
        return None

    # Price changed — append to state JSON
    history.append({"price": deal.price, "ts": now})
    prices[dedup_key] = history[-10:]  # Keep last 10 entries
    state["prices"] = prices

    if deal.price < last_price:
        drop_abs = last_price - deal.price
        drop_pct = (drop_abs / last_price) * 100 if last_price > 0 else 0

        # Check thresholds (OR logic)
        if drop_pct >= pt_config["min_drop_percent"] or drop_abs >= pt_config["min_drop_amount"]:
            # Check if this is the lowest ever price via SQLite
            is_lowest = False
            if db:
                try:
                    lowest = db.get_lowest_price(deal.id)
                    if lowest is None or deal.price <= lowest:
                        is_lowest = True
                except Exception:
                    pass
            else:
                # Fallback: check state JSON history
                all_prices = [h["price"] for h in history]
                if deal.price <= min(all_prices):
                    is_lowest = True

            result = {
                "type": "drop",
                "old_price": last_price,
                "new_price": deal.price,
                "diff_pln": drop_abs,
                "diff_percent": round(drop_pct, 1),
                "is_lowest_ever": is_lowest,
            }
            logger.info(
                f"Price drop detected for '{deal.title[:60]}': "
                f"{drop_abs} PLN ({last_price} -> {deal.price})"
            )
            return result
    else:
        increase_abs = deal.price - last_price
        increase_pct = (increase_abs / last_price) * 100 if last_price > 0 else 0
        logger.info(f"Price increased for '{deal.title[:60]}': {last_price} -> {deal.price}")

        if pt_config["track_increases"]:
            return {
                "type": "increase",
                "old_price": last_price,
                "new_price": deal.price,
                "diff_pln": increase_abs,
                "diff_percent": round(increase_pct, 1),
                "is_lowest_ever": False,
            }

    return None


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


def fetch_all_deals(profile: dict) -> tuple[list, dict[str, bool], list[str]]:
    """Fetch deals from all configured sources.

    Returns (deals, source_results, errors) where source_results maps
    source_name -> True/False for health tracking.
    """
    sources_config = profile.get("sources", {})
    all_deals = []
    source_results: dict[str, bool] = {}
    errors: list[str] = []

    for source_name, source_config in sources_config.items():
        source_class = SOURCE_REGISTRY.get(source_name)
        if not source_class:
            logger.warning(f"Unknown source: {source_name}")
            continue

        try:
            source = source_class()
            deals = source.fetch_deals(source_config)
            all_deals.extend(deals)
            source_results[source_name] = True
            logger.info(f"Source {source_name}: {len(deals)} deals fetched")
        except Exception as e:
            logger.error(f"Source {source_name} failed: {e}", exc_info=True)
            source_results[source_name] = False
            errors.append(f"{source_name}: {e}")
            # Graceful degradation — continue with other sources

    return all_deals, source_results, errors


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


def run_profile(
    profile_name: str, verify: bool = False, validate_only: bool = False
) -> dict | None:
    """Run a single profile. Returns profile result dict for health tracking (None in verify/validate mode)."""
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
            return None
        logger.error(f"Profile '{profile_name}' has validation errors, skipping")
        return {"status": "error", "deals_found": 0, "new_alerts": 0, "errors": [f"validation: {e}" for e in errors], "source_results": {}}

    if validate_only:
        print(f"\u2705 Profile '{profile_name}' is valid")
        return None

    emoji = profile.get("emoji", "\U0001f50d")
    logger.info(f"{'=' * 60}")
    logger.info(f"Running profile: {profile_name} {emoji} (verify={verify})")

    # Fetch
    all_deals, source_results, fetch_errors = fetch_all_deals(profile)
    unique_deals = deduplicate(all_deals)
    logger.info(f"Total unique deals: {len(unique_deals)}")

    # Get filter
    deal_filter = get_filter(profile)

    if verify:
        _run_verify(unique_deals, deal_filter, profile)
        return None

    # Normal mode
    num_alerts = _run_normal(unique_deals, deal_filter, profile, profile_name)

    status = "ok" if not fetch_errors else ("partial" if unique_deals else "error")
    return {
        "status": status,
        "deals_found": len(unique_deals),
        "new_alerts": num_alerts,
        "errors": fetch_errors,
        "source_results": source_results,
    }


def _run_normal(deals: list, deal_filter: BaseFilter, profile: dict, profile_name: str) -> int:
    """Normal mode — find new deals, score, and notify. Returns number of alerts sent."""
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
    price_drop_alerts: list[dict] = []

    try:
        for deal in deals:
            if deal.id in seen:
                # Even for seen deals, check price changes
                price_change = check_price_changes(deal, state, profile_name, profile, db)
                if price_change and price_change["type"] == "drop":
                    price_drop_alerts.append({"deal": deal, "price_change": price_change})
                continue

            seen[deal.id] = now

            result = deal_filter.score_deal(deal)

            if result.rejected:
                logger.debug(f"Rejected: {deal.title[:60]} ({result.reject_reason})")
                continue

            # Price drop detection for new deals too
            price_change = check_price_changes(deal, state, profile_name, profile, db)

            # Persist to SQLite
            if db and result.score >= threshold:
                category = _detect_category(deal, profile, profile_name)
                db.upsert_deal(deal, profile_name, result.score, category)

            if result.score >= threshold:
                alert_plus = list(result.plus)
                if price_change and price_change["type"] == "drop":
                    alert_plus.append(
                        f"price drop {price_change['diff_pln']} PLN "
                        f"({price_change['old_price']} -> {price_change['new_price']})"
                    )
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

    # Send price drop alerts first (higher priority), limited by max_alerts
    if price_drop_alerts:
        price_drop_alerts.sort(key=lambda x: x["price_change"]["diff_percent"], reverse=True)
    if telegram and price_drop_alerts:
        for pda in price_drop_alerts[:max_alerts]:
            telegram.send_price_drop_alert(
                pda["deal"],
                pda["price_change"],
                topic_id=tg_topic,
                emoji=emoji,
                currency=currency,
            )
        logger.info(f"Sent {min(len(price_drop_alerts), max_alerts)} price drop alerts for {profile_name}")

    # Console output for price drops
    for pda in price_drop_alerts:
        d = pda["deal"]
        pc = pda["price_change"]
        old_str = f"{pc['old_price']:,} {currency}".replace(",", " ")
        new_str = f"{pc['new_price']:,} {currency}".replace(",", " ")
        print(f"{emoji} \U0001f4c9 PRICE DROP: {d.title[:60]}")
        print(f"  {old_str} -> {new_str} (-{pc['diff_percent']:.0f}%, -{pc['diff_pln']} {currency})")
        if pc.get("is_lowest_ever"):
            print(f"  \U0001f525 Najniższa cena w historii!")
        print(f"  {d.link}")
        print()

    if not alerts and not price_drop_alerts:
        print(f"{emoji} No new deals for profile {profile_name}.")
        logger.info(f"No new alerts for {profile_name}")
        return 0

    if not alerts:
        return len(price_drop_alerts)

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

    total_alerts = len(alerts) + len(price_drop_alerts)
    logger.info(f"Profile {profile_name}: {len(alerts)} new deal alerts, {len(price_drop_alerts)} price drop alerts")
    return total_alerts


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


def run_digest() -> None:
    """Generate and send weekly price digest from SQLite price_history."""
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not tg_token or not tg_chat:
        logger.warning("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set — cannot send digest")
        print("Warning: Telegram not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")
        return

    db: SQLiteStorage | None = None
    try:
        db = SQLiteStorage(DB_PATH)
    except Exception as e:
        logger.error(f"SQLite unavailable, cannot generate digest: {e}")
        print("Error: SQLite database unavailable for digest generation.")
        sys.exit(1)

    try:
        drops = db.get_price_drops(days=7)
    finally:
        db.close()

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
        print(f"  \U0001f4c9 {d['title'][:60]}: {old_str} -> {new_str} (-{d['diff_percent']}%){lowest}")

    # Send Telegram digest
    topic_id_str = os.environ.get("TELEGRAM_TOPIC_ID")
    topic_id = int(topic_id_str) if topic_id_str else None
    telegram = TelegramNotifier(tg_token, tg_chat)
    telegram.send_digest(drops, topic_id=topic_id)
    print(f"\nDigest sent to Telegram ({len(drops)} drops).")


def _run_with_health_tracking(profile_names: list[str], verify: bool = False) -> None:
    """Run profiles and write health.json with results."""
    start = time.monotonic()
    existing_health = load_health()

    profile_results: dict[str, dict] = {}
    all_source_results: dict[str, bool] = {}

    for profile_name in profile_names:
        try:
            result = run_profile(profile_name, verify=verify)
            if result is not None:
                source_results = result.get("source_results", {})
                profile_results[profile_name] = {
                    k: v for k, v in result.items() if k != "source_results"
                }
                # Merge source results (last write wins per source, which is fine)
                all_source_results.update(source_results)
        except Exception as e:
            logger.error(f"Profile {profile_name} failed: {e}", exc_info=True)
            profile_results[profile_name] = {
                "status": "error",
                "deals_found": 0,
                "new_alerts": 0,
                "errors": [str(e)],
            }

    # Skip health tracking for verify mode
    if verify or not profile_results:
        return

    duration = time.monotonic() - start
    sources_health = update_sources_health(existing_health, all_source_results)
    health_data = build_health_data(profile_results, sources_health, duration, __version__)
    save_health(health_data)

    # Alert on sources with consecutive failures >= threshold
    failing_sources = get_failing_sources(sources_health)
    if failing_sources:
        _send_source_failure_alert(failing_sources, sources_health)


def _send_source_failure_alert(failing_sources: list[str], sources_health: dict) -> None:
    """Send Telegram alert for sources with too many consecutive failures."""
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not tg_token or not tg_chat:
        return

    topic_id_str = os.environ.get("TELEGRAM_TOPIC_ID")
    topic_id = int(topic_id_str) if topic_id_str else None

    telegram = TelegramNotifier(tg_token, tg_chat)
    lines = []
    for name in failing_sources:
        data = sources_health[name]
        count = data.get("consecutive_failures", 0)
        last = data.get("last_success", "never")
        lines.append(f"  • {name}: {count} consecutive failures (last success: {last})")

    msg = f"⚠️ Deal Hunter: source failures detected!\n\n" + "\n".join(lines)
    telegram.send_text(msg, topic_id=topic_id)


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
    parser.add_argument("--health", action="store_true", help="Show health status of last run")
    parser.add_argument(
        "--watchdog", action="store_true", help="Check if last run is fresh, alert if stale"
    )
    parser.add_argument(
        "--digest", action="store_true", help="Send weekly price drop digest from SQLite"
    )
    parser.add_argument("--version", action="version", version=f"Deal Hunter {__version__}")

    args = parser.parse_args()

    if args.init:
        from utils.init_profile import run_init

        run_init()
        return

    if args.health:
        sys.exit(print_health_status())

    if args.watchdog:
        ok, message = check_watchdog()
        if ok:
            print("OK")
            sys.exit(0)
        else:
            print(f"STALE: {message}")
            # Send Telegram alert
            tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
            tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "")
            if tg_token and tg_chat:
                topic_id_str = os.environ.get("TELEGRAM_TOPIC_ID")
                topic_id = int(topic_id_str) if topic_id_str else None
                telegram = TelegramNotifier(tg_token, tg_chat)
                telegram.send_text(f"⚠️ Deal Hunter watchdog: {message}", topic_id=topic_id)
            sys.exit(1)

    if args.digest:
        run_digest()
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
        profiles = list_profiles(include_disabled=False)
        _run_with_health_tracking(profiles, verify=args.verify)
        return

    if args.profile:
        _run_with_health_tracking([args.profile], verify=args.verify)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
