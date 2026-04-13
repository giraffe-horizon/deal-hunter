#!/usr/bin/env python3
"""Deal Hunter — universal multi-source deal monitor.

Profiles define products, sources, scoring rules, and notification targets.
This module is the CLI entrypoint; business logic lives in services/.
"""

import argparse
import contextlib
import importlib.metadata
import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from filters import FILTER_REGISTRY
from storage.database import get_session
from storage.repositories import (
    AlertQueueRepository,
    DealRepository,
    PriceRepository,
    SeenDealRepository,
    WatchlistRepository,
)

__version__ = "0.13.0"  # maintained by semantic-release
with contextlib.suppress(importlib.metadata.PackageNotFoundError):
    __version__ = importlib.metadata.version("deal-hunter")

from cli.verify import (
    run_verify,
)
from notifiers.telegram import TelegramNotifier
from services.alerter import AlertService
from services.fetcher import DealFetcher
from services.health_tracker import HealthTracker
from services.price_tracker import PriceTracker
from services.profile_manager import ProfileManager
from services.scorer import ScoringService
from sources import SOURCE_REGISTRY

# ──────────────── SETUP ────────────────

BASE_DIR = Path(__file__).parent
PROFILES_DIR = BASE_DIR / "profiles"

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


def validate_environment() -> None:
    """Check required environment variables and warn about missing ones."""
    required = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        logger.warning(
            "Missing env vars: %s — Telegram alerts will be disabled", ", ".join(missing)
        )


def _parse_topic_id() -> int | None:
    """Parse TELEGRAM_TOPIC_ID from environment, returning None if unset or invalid."""
    raw = os.environ.get("TELEGRAM_TOPIC_ID")
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        logger.warning(f"Invalid TELEGRAM_TOPIC_ID: {raw!r}, ignoring")
        return None


def _create_telegram() -> TelegramNotifier | None:
    """Create a TelegramNotifier if credentials are configured."""
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if tg_token and tg_chat:
        return TelegramNotifier(tg_token, tg_chat)
    return None


# ──────────────── SERVICE FACTORIES ────────────────

_profile_mgr = ProfileManager(PROFILES_DIR)
_fetcher = DealFetcher(SOURCE_REGISTRY)
_scoring = ScoringService(FILTER_REGISTRY)


def _health_tracker() -> HealthTracker:
    state_dir = Path(os.environ.get("DEAL_HUNTER_STATE_DIR", str(BASE_DIR / "state")))
    return HealthTracker(state_dir / "health.json")


# ──────────────── RUN MODES ────────────────


def run_profile(
    profile_name: str,
    verify: bool = False,
    validate_only: bool = False,
    verbose: bool = False,
    top: int | None = None,
) -> dict | None:
    """Run a single profile.

    Returns profile result dict for health tracking (None in verify/validate mode).
    """
    profile = _profile_mgr.load(profile_name)
    if profile is None:
        logger.error(f"Profile not found or empty: {profile_name}")
        sys.exit(1)

    # Validate profile
    errors = _profile_mgr.validate(profile)
    if errors:
        for err in errors:
            logger.error(f"Profile '{profile_name}' validation: {err}")
        if validate_only:
            print(f"\u274c Profile '{profile_name}' has {len(errors)} error(s):")
            for err in errors:
                print(f"  - {err}")
            return None
        logger.error(f"Profile '{profile_name}' has validation errors, skipping")
        return {
            "status": "error",
            "deals_found": 0,
            "new_alerts": 0,
            "errors": [f"validation: {e}" for e in errors],
            "source_results": {},
        }

    if validate_only:
        print(f"\u2705 Profile '{profile_name}' is valid")
        return None

    emoji = profile.get("emoji", "\U0001f50d")
    logger.info(f"{'=' * 60}")
    logger.info(f"Running profile: {profile_name} {emoji} (verify={verify})")

    # Fetch and deduplicate
    all_deals, source_results, fetch_errors = _fetcher.fetch_all(profile)
    dedup_config = profile.get("dedup", {})
    unique_deals = _fetcher.deduplicate(all_deals, dedup_config=dedup_config)
    logger.info(f"Total unique deals: {len(unique_deals)}")

    # Get filter
    deal_filter = _scoring.get_filter(profile)

    if verify:
        run_verify(unique_deals, deal_filter, profile, verbose=verbose, top=top)
        return None

    # ── Normal mode — score, check prices, persist, notify ──
    currency = profile.get("currency", "PLN")
    threshold = profile.get("score_threshold", 50)
    threshold_alert = profile.get("score_threshold_alert", 100)
    tg_config = profile.get("telegram", {})
    tg_topic = tg_config.get("topic_id")
    max_alerts = tg_config.get("max_alerts", 5)

    telegram = _create_telegram()
    alerts: list[dict] = []
    price_drop_alerts: list[dict] = []

    with get_session() as session:
        seen_repo = SeenDealRepository(session)
        deal_repo = DealRepository(session)
        price_repo = PriceRepository(session)
        watchlist_repo = WatchlistRepository(session)
        alert_repo = AlertQueueRepository(session)

        price_tracker = PriceTracker(price_repo)
        alert_service = AlertService(telegram, alert_repo)

        seen_ids = seen_repo.get_seen_ids(profile_name)

        # Flush queued alerts from previous quiet hours
        alert_service.flush_queued(profile_name, profile, tg_topic, max_alerts)

        for deal in unique_deals:
            if deal.id in seen_ids:
                # Even for seen deals, check price changes
                pc = price_tracker.check_price_change(deal, profile)
                if pc and pc.type == "drop":
                    price_drop_alerts.append(
                        {
                            "deal": deal,
                            "price_change": {
                                "type": pc.type,
                                "old_price": pc.old_price,
                                "new_price": pc.new_price,
                                "diff_pln": pc.diff_pln,
                                "diff_percent": pc.diff_percent,
                                "is_lowest_ever": pc.is_lowest_ever,
                            },
                        }
                    )
                continue

            seen_repo.mark_seen(deal.id, profile_name, f"{deal.title[:60]}|{deal.price}")

            result = deal_filter.score_deal(deal)

            if result.rejected:
                logger.debug(f"Rejected: {deal.title[:60]} ({result.reject_reason})")
                continue

            # Price drop detection for new deals too
            pc = price_tracker.check_price_change(deal, profile)

            # Persist to database
            if result.score >= threshold:
                category = _scoring.detect_category(deal, profile, profile_name)
                deal_repo.upsert(
                    id=deal.id,
                    title=deal.title,
                    price=deal.price,
                    link=deal.link,
                    source=deal.source,
                    description=deal.description,
                    image_url=deal.image_url,
                    profile=profile_name,
                    score=result.score,
                    category=category,
                )
                # Check watchlist triggers
                trigger = watchlist_repo.check_trigger(deal.id, deal.price)
                if trigger and telegram:
                    telegram.send_watchlist_alert(
                        deal,
                        target_price=trigger["target_price"],
                        current_price=deal.price,
                        topic_id=tg_topic,
                        currency=currency,
                    )
                    watchlist_repo.mark_triggered(deal.id)
                    logger.info(
                        f"Watchlist triggered: {deal.title[:40]} "
                        f"(target: {trigger['target_price']}, current: {deal.price})"
                    )

            if result.score >= threshold:
                alert_plus = list(result.plus)
                if pc and pc.type == "drop":
                    alert_plus.append(
                        f"price drop {pc.diff_pln} PLN ({pc.old_price} -> {pc.new_price})"
                    )
                alerts.append(
                    {
                        "deal": deal,
                        "score": result.score,
                        "plus": alert_plus,
                        "minus": result.minus,
                    }
                )

        # Send price drop alerts (higher priority)
        alert_service.send_price_drop_alerts(
            price_drop_alerts, profile, profile_name, tg_topic, max_alerts
        )

        # Send deal alerts
        alert_service.send_deal_alerts(alerts, profile, profile_name, tg_topic, max_alerts)

    # Console output for price drops
    for pda in price_drop_alerts:
        d = pda["deal"]
        pc_dict = pda["price_change"]
        old_str = f"{pc_dict['old_price']:,} {currency}".replace(",", " ")
        new_str = f"{pc_dict['new_price']:,} {currency}".replace(",", " ")
        print(f"{emoji} \U0001f4c9 PRICE DROP: {d.title[:60]}")
        print(
            f"  {old_str} -> {new_str}"
            f" (-{pc_dict['diff_percent']:.0f}%, -{pc_dict['diff_pln']} {currency})"
        )
        if pc_dict.get("is_lowest_ever"):
            print("  \U0001f525 Najniższa cena w historii!")
        print(f"  {d.link}")
        print()

    if not alerts and not price_drop_alerts:
        print(f"{emoji} No new deals for profile {profile_name}.")
        logger.info(f"No new alerts for {profile_name}")
        num_alerts = 0
    elif not alerts:
        num_alerts = len(price_drop_alerts)
    else:
        # Console output for deal alerts
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

        num_alerts = len(alerts) + len(price_drop_alerts)
        n_deals = len(alerts)
        n_drops = len(price_drop_alerts)
        logger.info(
            f"Profile {profile_name}: {n_deals} new deal alerts, {n_drops} price drop alerts"
        )

    status = "ok" if not fetch_errors else ("partial" if unique_deals else "error")
    return {
        "status": status,
        "deals_found": len(unique_deals),
        "new_alerts": num_alerts,
        "errors": fetch_errors,
        "source_results": source_results,
    }


def _run_with_health_tracking(
    profile_names: list[str],
    verify: bool = False,
    verbose: bool = False,
    top: int | None = None,
) -> None:
    """Run profiles and write health.json with results."""
    start = time.monotonic()
    ht = _health_tracker()
    existing_health = ht.load()

    profile_results: dict[str, dict] = {}
    all_source_results: dict[str, bool] = {}

    for profile_name in profile_names:
        try:
            result = run_profile(profile_name, verify=verify, verbose=verbose, top=top)
            if result is not None:
                source_results = result.get("source_results", {})
                profile_results[profile_name] = {
                    k: v for k, v in result.items() if k != "source_results"
                }
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
    sources_health = ht.update_sources(existing_health, all_source_results)
    health_data = ht.build_data(profile_results, sources_health, duration, __version__)
    ht.save(health_data)

    # Alert on sources with consecutive failures >= threshold
    failing_sources = ht.get_failing_sources(sources_health)
    if failing_sources:
        telegram = _create_telegram()
        if telegram:
            topic_id = _parse_topic_id()
            alert_repo_stub = None  # Not needed for source failure alerts
            alert_svc = AlertService(telegram, alert_repo_stub)
            alert_svc.send_source_failure_alert(failing_sources, sources_health, topic_id)


# ──────────────── CLI COMMANDS ────────────────


def run_digest() -> None:
    """Generate and send weekly price digest from SQLite price_history."""
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not tg_token or not tg_chat:
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
    topic_id = _parse_topic_id()
    telegram = TelegramNotifier(tg_token, tg_chat)
    telegram.send_digest(drops, topic_id=topic_id)
    print(f"\nDigest sent to Telegram ({len(drops)} drops).")

    # Generate and send digest bar chart
    try:
        from visualization.charts import generate_digest_chart

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


def run_price_chart(deal_id: str) -> None:
    """Generate a price history chart for a deal and send to Telegram."""
    from visualization.charts import generate_price_chart

    with get_session() as session:
        try:
            chart_path = generate_price_chart(deal_id, session)
        except (ValueError, ImportError) as e:
            print(f"Error: {e}")
            sys.exit(1)

    print(f"Chart saved to {chart_path}")

    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if tg_token and tg_chat:
        topic_id = _parse_topic_id()
        telegram = TelegramNotifier(tg_token, tg_chat)
        telegram.send_photo(
            str(chart_path),
            caption=f"\U0001f4c8 Historia cen: {deal_id}",
            topic_id=topic_id,
        )
        print("Chart sent to Telegram.")
    else:
        print("Telegram not configured — chart not sent.")


def run_trend_chart(profile_name: str) -> None:
    """Generate a trend chart for a profile and send to Telegram."""
    from visualization.charts import generate_trend_chart

    with get_session() as session:
        try:
            chart_path = generate_trend_chart(profile_name, session)
        except (ValueError, ImportError) as e:
            print(f"Error: {e}")
            sys.exit(1)

    print(f"Chart saved to {chart_path}")

    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    tg_chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if tg_token and tg_chat:
        topic_id = _parse_topic_id()
        telegram = TelegramNotifier(tg_token, tg_chat)
        telegram.send_photo(
            str(chart_path),
            caption=f"\U0001f4ca Trend cenowy: {profile_name}",
            topic_id=topic_id,
        )
        print("Chart sent to Telegram.")
    else:
        print("Telegram not configured — chart not sent.")


# ──────────────── CLI ENTRYPOINT ────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Deal Hunter \u2014 multi-source deal monitor")
    parser.add_argument("--profile", "-p", type=str, help="Profile name to run")
    parser.add_argument("--all", "-a", action="store_true", help="Run all profiles")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify mode (show all deals with scores, no state)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose scoring breakdown (use with --verify)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=None,
        help="Limit output to top N deals (default: all in verbose, 20 otherwise)",
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
    parser.add_argument(
        "--price-chart",
        type=str,
        metavar="DEAL_ID",
        help="Generate price history chart for a deal and send to Telegram",
    )
    parser.add_argument(
        "--trend-chart",
        type=str,
        metavar="PROFILE",
        help="Generate trend chart for a profile and send to Telegram",
    )
    parser.add_argument("--version", action="version", version=f"Deal Hunter {__version__}")

    args = parser.parse_args()

    validate_environment()

    if args.init:
        from utils.init_profile import run_init

        run_init()
        return

    if args.health:
        ht = _health_tracker()
        sys.exit(ht.print_status())

    if args.watchdog:
        ht = _health_tracker()
        ok, message = ht.check_watchdog()
        if ok:
            print("OK")
            sys.exit(0)
        else:
            print(f"STALE: {message}")
            telegram = _create_telegram()
            if telegram:
                topic_id = _parse_topic_id()
                telegram.send_text(
                    f"\u26a0\ufe0f Deal Hunter watchdog: {message}", topic_id=topic_id
                )
            sys.exit(1)

    if args.digest:
        run_digest()
        return

    if args.price_chart:
        run_price_chart(args.price_chart)
        return

    if args.trend_chart:
        run_trend_chart(args.trend_chart)
        return

    if args.list:
        profiles = _profile_mgr.list_all()
        print("Available profiles:")
        for p in profiles:
            prof = _profile_mgr.load(p)
            if prof:
                print(f"  {prof.get('emoji', '\U0001f50d')} {p}")
        return

    if args.validate:
        if args.profile:
            run_profile(args.profile, validate_only=True)
        elif args.all:
            for profile_name in _profile_mgr.list_all():
                run_profile(profile_name, validate_only=True)
        else:
            print("Usage: --validate requires --profile or --all")
        return

    if args.all:
        profiles = _profile_mgr.list_all(include_disabled=False)
        _run_with_health_tracking(profiles, verify=args.verify, verbose=args.verbose, top=args.top)
        return

    if args.profile:
        _run_with_health_tracking(
            [args.profile], verify=args.verify, verbose=args.verbose, top=args.top
        )
        return

    parser.print_help()


if __name__ == "__main__":
    main()
