"""Verify mode output -- scoring breakdown display."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from deal_hunter.domain.scoring.base import BaseFilter


def format_breakdown_line(entry: dict) -> str:
    """Format a single breakdown entry as a text line."""
    points = entry["points"]
    rule = entry["rule"]
    source = entry.get("source", "")
    match = entry.get("match", "")
    entry_type = entry.get("type", "")

    sign = f"+{points}" if points > 0 else str(points)

    if entry_type == "budget":
        label = f"Budget: {match}"
        return f"\u2502  {sign:>4}  {label}"
    if entry_type == "temperature":
        return f"\u2502  {sign:>4}  Temperature: {match}"
    if entry_type == "excluded":
        return f"\u2502  {sign:>4}  EXCLUDED: {rule} ({source} match)"
    if entry_type == "required_any":
        return f"\u2502  {sign:>4}  REJECTED: none of required_any matched"
    if entry_type in ("size", "color", "tire", "race"):
        return f"\u2502  {sign:>4}  {rule}: {match}"
    if entry_type == "regex":
        return f"\u2502  {sign:>4}  {rule} ({source} regex: {match})"
    # keyword / penalty
    source_hint = f" ({source} match)" if source else ""
    return f"\u2502  {sign:>4}  {rule}{source_hint}"


def _print_verbose_plain(
    scored: list[tuple],
    rejected_deals: list[tuple],
    threshold: int,
    threshold_alert: int,
    currency: str,
    top: int | None,
) -> None:
    """Print verbose scoring breakdown using box-drawing characters."""
    all_entries = list(scored)
    if top is not None:
        all_entries = all_entries[:top]

    for deal, result in all_entries:
        status = "\u2705" if result.score >= threshold else "\u274c"
        print(f"\u250c\u2500 {deal.title[:70]} \u2014 SCORE: {result.score} {status}")

        for entry in result.breakdown:
            print(format_breakdown_line(entry))

        tier = (
            "ALERT"
            if result.score >= threshold_alert
            else ("PASS" if result.score >= threshold else "BELOW")
        )
        print(f"\u2514\u2500 Final: {result.score} (threshold: {threshold}) \u2192 {tier} {status}")
        print()

    if rejected_deals:
        print(f"  --- REJECTED ({len(rejected_deals)}) ---\n")
        for deal, result in rejected_deals:
            print(f"\u250c\u2500 {deal.title[:70]} \u2014 REJECTED")
            if result.breakdown:
                for entry in result.breakdown:
                    print(format_breakdown_line(entry))
            print(f"\u2514\u2500 Reason: {result.reject_reason}")
            print()

    if top is not None and len(scored) > top:
        print(f"  ... and {len(scored) - top} more scored deals\n")


def _print_verbose_rich(
    scored: list[tuple],
    rejected_deals: list[tuple],
    threshold: int,
    threshold_alert: int,
    currency: str,
    top: int | None,
) -> None:
    """Print verbose scoring breakdown using the rich library."""
    from rich.console import Console
    from rich.panel import Panel

    console = Console()
    all_entries = list(scored)
    if top is not None:
        all_entries = all_entries[:top]

    for deal, result in all_entries:
        status = "\u2705" if result.score >= threshold else "\u274c"
        tier = (
            "ALERT"
            if result.score >= threshold_alert
            else ("PASS" if result.score >= threshold else "BELOW")
        )

        lines = []
        for entry in result.breakdown:
            points = entry["points"]
            sign = f"+{points}" if points > 0 else str(points)
            rule = entry["rule"]
            source = entry.get("source", "")
            match = entry.get("match", "")
            entry_type = entry.get("type", "")

            color = "green" if points > 0 else ("red" if points < 0 else "yellow")

            if entry_type == "budget":
                desc = f"Budget: {match}"
            elif entry_type == "temperature":
                desc = f"Temperature: {match}"
            elif entry_type == "excluded":
                desc = f"EXCLUDED: {rule} ({source} match)"
            elif entry_type == "required_any":
                desc = "REJECTED: none of required_any matched"
            elif entry_type in ("size", "color", "tire", "race"):
                desc = f"{rule}: {match}"
            elif entry_type == "regex":
                desc = f"{rule} ({source} regex: {match})"
            else:
                source_hint = f" ({source} match)" if source else ""
                desc = f"{rule}{source_hint}"

            lines.append(f"[{color}]{sign:>4}[/{color}]  {desc}")

        body = "\n".join(lines) if lines else "(no rules fired)"
        body += f"\n\nFinal: {result.score} (threshold: {threshold}) \u2192 {tier} {status}"

        border = "green" if result.score >= threshold else "red"
        title = f"{deal.title[:70]} \u2014 SCORE: {result.score} {status}"
        console.print(Panel(body, title=title, border_style=border, expand=False))

    if rejected_deals:
        lines = []
        for deal, result in rejected_deals:
            lines.append(f"[red]\u274c[/red] {deal.title[:60]} \u2014 {result.reject_reason}")
        console.print(
            Panel(
                "\n".join(lines),
                title=f"REJECTED ({len(rejected_deals)})",
                border_style="dim",
                expand=False,
            )
        )

    if top is not None and len(scored) > top:
        console.print(f"\n  ... and {len(scored) - top} more scored deals\n")


def print_verbose(
    scored: list[tuple],
    rejected_deals: list[tuple],
    threshold: int,
    threshold_alert: int,
    currency: str,
    top: int | None,
) -> None:
    """Print verbose scoring breakdown. Uses rich if available, falls back to plain text."""
    try:
        import rich  # noqa: F401

        _print_verbose_rich(scored, rejected_deals, threshold, threshold_alert, currency, top)
    except ImportError:
        _print_verbose_plain(scored, rejected_deals, threshold, threshold_alert, currency, top)


def run_verify(
    deals: list,
    deal_filter: BaseFilter,
    profile: dict,
    verbose: bool = False,
    top: int | None = None,
) -> None:
    """Verify mode -- analyze all deals without state tracking."""
    emoji = profile.get("emoji", "\U0001f50d")
    currency = profile.get("currency", "PLN")
    threshold = profile.get("score_threshold", 50)
    threshold_alert = profile.get("score_threshold_alert", 100)
    profile_name = profile.get("name", "unknown")

    print(f"\n{'=' * 60}")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"  {emoji} DEAL ANALYSIS \u2014 {profile_name.upper()} \u2014 {now_str}")
    print(f"  Found {len(deals)} deals")
    print(f"{'=' * 60}\n")

    scored: list[tuple] = []
    rejected_deals: list[tuple] = []

    for deal in deals:
        result = deal_filter.score_deal(deal)
        if result.rejected:
            rejected_deals.append((deal, result))
            continue
        scored.append((deal, result))

    scored.sort(key=lambda x: x[1].score, reverse=True)

    if verbose:
        print_verbose(scored, rejected_deals, threshold, threshold_alert, currency, top)
    else:
        if rejected_deals:
            print(f"  ({len(rejected_deals)} deals rejected)\n")

        limit = top if top is not None else 20
        for deal, result in scored[:limit]:
            price_str = (
                f"{deal.price:,} {currency}".replace(",", " ") if deal.price > 0 else "no price"
            )
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

        if top is not None and len(scored) > top:
            print(f"  ... and {len(scored) - top} more deals\n")
