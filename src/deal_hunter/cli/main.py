#!/usr/bin/env python3
"""Deal Hunter — universal multi-source deal monitor.

CLI entrypoint: argparse + dispatch.  Business logic lives in
``deal_hunter.services.hunt_service`` / ``digest_service`` / ``chart_service``.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.metadata
import logging
import sys

from deal_hunter.core.logging import setup_app_logging
from deal_hunter.core.settings import get_settings
from deal_hunter.services.chart_service import run_price_chart, run_trend_chart
from deal_hunter.services.digest_service import run_digest
from deal_hunter.services.hunt_service import run_profile, run_profiles
from deal_hunter.services.runtime import (
    get_health_tracker,
    get_profile_manager,
    get_telegram,
    get_topic_id,
)

__version__ = "0.14.1"  # maintained by semantic-release
with contextlib.suppress(importlib.metadata.PackageNotFoundError):
    __version__ = importlib.metadata.version("deal-hunter")

setup_app_logging()
logger = logging.getLogger("deal_hunter")


def validate_environment() -> None:
    """Check required environment variables and warn about missing ones."""
    s = get_settings()
    missing = []
    if not s.telegram_bot_token:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not s.telegram_chat_id:
        missing.append("TELEGRAM_CHAT_ID")
    if missing:
        logger.warning(
            "Missing env vars: %s — Telegram alerts will be disabled", ", ".join(missing)
        )


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
        from deal_hunter.utils.init_profile import run_init

        run_init()
        return

    if args.health:
        sys.exit(get_health_tracker().print_status())

    if args.watchdog:
        ok, message = get_health_tracker().check_watchdog()
        if ok:
            print("OK")
            sys.exit(0)
        print(f"STALE: {message}")
        telegram = get_telegram()
        if telegram:
            telegram.send_text(
                f"\u26a0\ufe0f Deal Hunter watchdog: {message}", topic_id=get_topic_id()
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

    profile_mgr = get_profile_manager()

    if args.list:
        print("Available profiles:")
        for p in profile_mgr.list_all():
            prof = profile_mgr.load(p)
            if prof:
                print(f"  {prof.get('emoji', '\U0001f50d')} {p}")
        return

    if args.validate:
        if args.profile:
            run_profile(args.profile, validate_only=True)
        elif args.all:
            for profile_name in profile_mgr.list_all():
                run_profile(profile_name, validate_only=True)
        else:
            print("Usage: --validate requires --profile or --all")
        return

    if args.all:
        profiles = profile_mgr.list_all(include_disabled=False)
        run_profiles(
            profiles, verify=args.verify, verbose=args.verbose, top=args.top, version=__version__
        )
        return

    if args.profile:
        run_profiles(
            [args.profile],
            verify=args.verify,
            verbose=args.verbose,
            top=args.top,
            version=__version__,
        )
        return

    parser.print_help()


if __name__ == "__main__":
    main()
