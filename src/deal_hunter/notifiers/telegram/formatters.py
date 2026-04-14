"""Polish-language HTML message formatters for Telegram notifications.

Pure functions — no I/O, no network. Each returns a Telegram-ready HTML string
(escaped, bounded to Telegram's 4096-char message limit).
"""

from __future__ import annotations

import html
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from deal_hunter.sources.base import Deal

_MAX_MSG_LEN = 3500  # Safety margin under Telegram's 4096 HTML cap


def _format_price(value: int, currency: str) -> str:
    """Format price as '1 234 PLN' or 'brak ceny' for 0/missing."""
    return f"{value:,} {currency}".replace(",", " ") if value > 0 else "brak ceny"


def _format_alt_links(deal: Deal, currency: str, include_price: bool = True) -> str:
    """Build the 'Też w:' line for cross-source alt_links, or '' if none."""
    if not hasattr(deal, "alt_links") or not deal.alt_links:
        return ""
    parts = []
    for alt in deal.alt_links:
        alt_source = html.escape(alt["source"])
        alt_link = html.escape(alt["link"])
        if include_price and alt.get("price"):
            alt_price = f"{alt['price']:,} {currency}".replace(",", " ")
            parts.append(f'<a href="{alt_link}">{alt_source}</a> ({html.escape(alt_price)})')
        else:
            parts.append(f'<a href="{alt_link}">{alt_source}</a>')
    return f"\n\U0001f517 Też w: {' | '.join(parts)}\n"


def format_deal_alert(
    deal: Deal,
    score: int,
    tier: str,
    plus: list[str],
    minus: list[str],
    emoji: str = "\U0001f525",
    size_warning: str = "",
    currency: str = "PLN",
) -> str:
    """Format the main deal alert (hot deal with score, plus/minus, link)."""
    price_str = _format_price(deal.price, currency)
    safe_title = html.escape(deal.title)
    safe_tier = html.escape(tier)

    msg = f"<b>{safe_tier}</b> (score: {score})\n"
    msg += f"{emoji} <b>{safe_title}</b>\n"

    if deal.regular_price > 0 and deal.price > 0:
        regular_str = f"{deal.regular_price:,} {currency}".replace(",", " ")
        discount = round((deal.regular_price - deal.price) / deal.regular_price * 100)
        msg += (
            f"\U0001f4b0 Cena: <b>{html.escape(price_str)}</b>"
            f" <s>{html.escape(regular_str)}</s> (-{discount}%)\n\n"
        )
    else:
        msg += f"\U0001f4b0 Cena: <b>{html.escape(price_str)}</b>\n\n"

    plus_with_warning = list(plus)
    if size_warning:
        plus_with_warning.append(size_warning)

    if plus_with_warning:
        safe_plus = [html.escape(p) for p in plus_with_warning[:6]]
        msg += f"\u2705 {', '.join(safe_plus)}\n"
    if minus:
        safe_minus = [html.escape(m) for m in minus[:4]]
        msg += f"\u26a0\ufe0f {', '.join(safe_minus)}\n"

    msg += _format_alt_links(deal, currency, include_price=True)

    safe_link = html.escape(deal.link)
    safe_source = html.escape(deal.source)
    msg += (
        f'\n\U0001f517 <a href="{safe_link}">LINK DO OKAZJI</a>'
        f" | \u0179r\u00f3d\u0142o: {safe_source}"
    )
    return msg


def format_summary(
    remaining_alerts: list[dict],
    emoji: str = "\U0001f525",
    currency: str = "PLN",
) -> str:
    """Format overflow-alerts summary (compact list when too many hits fire)."""
    if not remaining_alerts:
        return ""

    msg = f"{emoji} PODSUMOWANIE - {len(remaining_alerts)} dodatkowych ofert:\n\n"
    for i, alert in enumerate(remaining_alerts, 1):
        deal = alert["deal"]
        score = alert["score"]
        price_str = _format_price(deal.price, currency)

        safe_title = html.escape(deal.title[:80])
        safe_link = html.escape(deal.link)
        safe_source = html.escape(deal.source)
        msg += f"{i}. <b>{safe_title}</b>\n"
        msg += f"   \U0001f4b0 {html.escape(price_str)} | Score: {score}\n"
        msg += f'   \U0001f517 <a href="{safe_link}">Link</a> | {safe_source}\n\n'

        if len(msg) > _MAX_MSG_LEN:
            msg += f"... i {len(remaining_alerts) - i} wi\u0119cej ofert"
            break
    return msg


def format_price_drop(
    deal: Deal,
    price_change: dict,
    emoji: str = "\U0001f50d",
    currency: str = "PLN",
) -> str:
    """Format a price-drop alert for a known deal (with optional lowest-ever badge)."""
    old_str = f"{price_change['old_price']:,} {currency}".replace(",", " ")
    new_str = f"{price_change['new_price']:,} {currency}".replace(",", " ")
    diff_pln = price_change["diff_pln"]
    diff_pct = price_change["diff_percent"]
    diff_pln_str = f"{diff_pln:,}".replace(",", " ")

    safe_title = html.escape(deal.title)
    safe_link = html.escape(deal.link)
    safe_source = html.escape(deal.source)

    msg = f"{emoji} \U0001f4c9 <b>SPADEK CENY!</b>\n"
    msg += f"<b>{safe_title}</b>\n"
    msg += (
        f"{html.escape(old_str)} \u2192 <b>{html.escape(new_str)}</b>"
        f" (-{diff_pct:.0f}%, -{html.escape(diff_pln_str)} {html.escape(currency)})\n"
    )

    if price_change.get("is_lowest_ever"):
        msg += "\U0001f525 <b>Najni\u017csza cena w historii!</b>\n"

    msg += _format_alt_links(deal, currency, include_price=False)

    msg += (
        f'\n\U0001f517 <a href="{safe_link}">Link do oferty</a>'
        f" | \u0179r\u00f3d\u0142o: {safe_source}"
    )
    return msg


def format_watchlist_alert(
    deal: Deal,
    target_price: int,
    current_price: int,
    currency: str = "PLN",
) -> str:
    """Format watchlist target-price-hit alert."""
    target_str = f"{target_price:,} {currency}".replace(",", " ")
    current_str = f"{current_price:,} {currency}".replace(",", " ")

    safe_title = html.escape(deal.title)
    safe_link = html.escape(deal.link)

    msg = "\U0001f3af <b>CEL CENOWY OSIĄGNIĘTY</b>\n"
    msg += f"<b>{safe_title}</b>\n\n"
    msg += f"Twój próg: {html.escape(target_str)}\n"
    msg += f"Obecna cena: <b>{html.escape(current_str)}</b>\n"
    msg += f'\n\U0001f517 <a href="{safe_link}">Otwórz</a>'
    return msg


def format_digest(
    drops: list[dict],
    emoji: str = "\U0001f4ca",
    currency: str = "PLN",
) -> str:
    """Format weekly price-drop digest."""
    if not drops:
        return ""

    msg = f"{emoji} <b>Tygodniowy przegl\u0105d cen ({len(drops)} spadk\u00f3w)</b>\n\n"

    for drop in drops:
        safe_title = html.escape(drop["title"][:80])
        old_str = f"{drop['old_price']:,}".replace(",", " ")
        new_str = f"{drop['new_price']:,}".replace(",", " ")
        diff_pct = drop["diff_percent"]

        msg += (
            f"\U0001f4c9 {safe_title}: {html.escape(old_str)}"
            f" \u2192 {html.escape(new_str)} {html.escape(currency)} (-{diff_pct:.0f}%)"
        )
        if drop.get("is_lowest_ever"):
            msg += " \U0001f525"
        msg += "\n"

        if len(msg) > _MAX_MSG_LEN:
            msg += "\n... i wi\u0119cej spadk\u00f3w"
            break
    return msg
