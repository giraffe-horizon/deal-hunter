"""Hunt service: run profiles end-to-end (fetch → score → persist → alert).

Orchestrates the per-run workflow. The CLI dispatches into these functions
instead of owning the business logic itself.
"""

from __future__ import annotations

import logging
import sys
import time
from typing import TYPE_CHECKING

from deal_hunter.core.notification_config import load_global_config, resolve_for_profile
from deal_hunter.core.settings import get_settings
from deal_hunter.services.alerter import AlertService
from deal_hunter.services.price_tracker import PriceTracker
from deal_hunter.services.runtime import (
    get_fetcher,
    get_health_tracker,
    get_profile_manager,
    get_scoring_service,
    get_telegram,
    get_topic_id,
)
from deal_hunter.storage.database import get_session
from deal_hunter.storage.repositories import (
    AlertQueueRepository,
    OfferRepository,
    PriceRepository,
    SeenDealRepository,
    SentNotificationRepository,
    WatchlistRepository,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def run_profile(
    profile_name: str,
    *,
    verify: bool = False,
    validate_only: bool = False,
    verbose: bool = False,
    top: int | None = None,
) -> dict | None:
    """Run a single profile.

    Returns profile result dict for health tracking (None in verify/validate mode).
    """
    profile_mgr = get_profile_manager()
    fetcher = get_fetcher()
    scoring = get_scoring_service()

    profile = profile_mgr.load(profile_name)
    if profile is None:
        logger.error(f"Profile not found or empty: {profile_name}")
        sys.exit(1)

    # Validate profile
    errors = profile_mgr.validate(profile)
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
    all_deals, source_results, fetch_errors = fetcher.fetch_all(profile)
    dedup_config = profile.get("dedup", {})
    unique_deals = fetcher.deduplicate(all_deals, dedup_config=dedup_config)
    logger.info(f"Total unique deals: {len(unique_deals)}")

    # Get filter
    deal_filter = scoring.get_filter(profile)

    if verify:
        # Local import to avoid loading verify formatting until we need it.
        from deal_hunter.cli.verify import run_verify

        run_verify(unique_deals, deal_filter, profile, verbose=verbose, top=top)
        return None

    # ── Normal mode — score, check prices, persist, notify ──
    currency = profile.get("currency", "PLN")
    threshold = profile.get("score_threshold", 50)
    threshold_alert = profile.get("score_threshold_alert", 100)
    tg_config = profile.get("telegram", {})
    tg_topic = tg_config.get("topic_id")
    max_alerts = tg_config.get("max_alerts", 5)

    telegram = get_telegram()
    alerts: list[dict] = []
    price_drop_alerts: list[dict] = []

    # Set profile context on the fetcher for ingest_one to persist profile on Offer rows
    fetcher.profile_name = profile_name

    with get_session() as session:
        seen_repo = SeenDealRepository(session)
        price_repo = PriceRepository(session)
        watchlist_repo = WatchlistRepository(session)
        alert_repo = AlertQueueRepository(session)
        offer_repo = OfferRepository(session)
        sent_repo = SentNotificationRepository(session)
        global_notif = load_global_config(get_settings().base_dir / "config" / "notifications.yaml")
        notification_config = resolve_for_profile(global_notif, profile)

        price_tracker = PriceTracker(price_repo)
        alert_service = AlertService(
            telegram, alert_repo, offer_repo=offer_repo, sent_repo=sent_repo
        )

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
                category = scoring.detect_category(deal, profile, profile_name)
                fetcher.ingest_one(
                    session,
                    deal,
                    profile=profile,
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
                        profile=profile_name,
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
            price_drop_alerts,
            profile,
            profile_name,
            tg_topic,
            max_alerts,
            notification_config=notification_config,
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


def run_profiles(
    profile_names: list[str],
    *,
    verify: bool = False,
    verbose: bool = False,
    top: int | None = None,
    version: str = "",
) -> None:
    """Run one or more profiles and write health.json with aggregate results.

    `version` is embedded into health.json; pass deal_hunter.__version__ from CLI.
    """
    start = time.monotonic()
    ht = get_health_tracker()
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
    health_data = ht.build_data(profile_results, sources_health, duration, version)
    ht.save(health_data)

    # Alert on sources with consecutive failures >= threshold
    failing_sources = ht.get_failing_sources(sources_health)
    if failing_sources:
        telegram = get_telegram()
        if telegram:
            topic_id = get_topic_id()
            alert_svc = AlertService(telegram, None)  # No queue needed for source alerts
            alert_svc.send_source_failure_alert(failing_sources, sources_health, topic_id)
