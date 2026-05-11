"""Slash-command handlers for the feedback bot."""

from __future__ import annotations

import html
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import ContextTypes

from deal_hunter.storage.database import get_session
from deal_hunter.storage.repositories import (
    FeedbackRepository,
    OfferRepository,
    WatchlistRepository,
)

_MAX_MSG_LEN = 3500  # Safety margin under Telegram's 4096 HTML cap


async def cmd_watch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/watch <deal_id> — mark deal as watching."""
    if not context.args:
        await update.message.reply_text("Użycie: /watch <deal_id>")
        return

    deal_id = context.args[0]
    with get_session() as session:
        found = OfferRepository(session).update_status(deal_id, "watching")
        if not found:
            await update.message.reply_text(f"Nie znaleziono oferty: {html.escape(deal_id)}")
            return
        FeedbackRepository(session).record(deal_id, "watch")
        await update.message.reply_text(
            f"\u2b50 Oferta {html.escape(deal_id)} dodana do obserwowanych"
        )


async def cmd_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/skip <deal_id> — mark deal as rejected."""
    if not context.args:
        await update.message.reply_text("Użycie: /skip <deal_id>")
        return

    deal_id = context.args[0]
    with get_session() as session:
        found = OfferRepository(session).update_status(deal_id, "rejected")
        if not found:
            await update.message.reply_text(f"Nie znaleziono oferty: {html.escape(deal_id)}")
            return
        FeedbackRepository(session).record(deal_id, "skip")
        await update.message.reply_text(f"\U0001f44e Oferta {html.escape(deal_id)} pominięta")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/status — show feedback summary."""
    with get_session() as session:
        deal_repo = OfferRepository(session)
        stats = FeedbackRepository(session).get_stats()
        watching = len(deal_repo.get_by_status("watching", limit=10000))
        rejected = len(deal_repo.get_by_status("rejected", limit=10000))
        total = len(deal_repo.get_filtered())

        msg = "\U0001f4ca <b>Status bazy ofert</b>\n\n"
        msg += f"\u2b50 Obserwowane: <b>{watching}</b>\n"
        msg += f"\U0001f44e Pominięte: <b>{rejected}</b>\n"
        msg += f"\U0001f4e6 Łącznie w bazie: <b>{total}</b>\n"

        if stats:
            msg += "\n<b>Akcje feedback:</b>\n"
            for action, count in sorted(stats.items()):
                msg += f"  {action}: {count}\n"

        await update.message.reply_text(msg, parse_mode="HTML")


async def cmd_target(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/target <deal_id> <price> — set a target price for a deal."""
    if len(context.args) < 2:
        await update.message.reply_html(
            "Użycie: <code>/target &lt;deal_id&gt; &lt;cena&gt;</code>\n"
            "Przykład: <code>/target pepper:12345 8000</code>"
        )
        return

    deal_id = context.args[0]
    try:
        target_price = int(context.args[1])
    except ValueError:
        await update.message.reply_html("❌ Cena musi być liczbą całkowitą (w PLN).")
        return

    if target_price <= 0:
        await update.message.reply_html("❌ Cena musi być większa od 0.")
        return

    with get_session() as session:
        result = WatchlistRepository(session).add(deal_id, target_price)

    if result:
        price_str = f"{target_price:,} PLN".replace(",", " ")
        await update.message.reply_html(
            f"\U0001f3af Ustawiono cel cenowy: <b>{html.escape(price_str)}</b>\n"
            f"Deal: <code>{html.escape(deal_id)}</code>\n"
            f"Powiadomię Cię gdy cena spadnie do tego poziomu."
        )
    else:
        await update.message.reply_html(
            f"\u26a0\ufe0f Deal <code>{html.escape(deal_id)}</code>"
            f" jest już na liście obserwowanych."
        )


async def cmd_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/watchlist — show all deals with status='watching'."""
    with get_session() as session:
        deals = OfferRepository(session).get_by_status("watching", limit=20)
        if not deals:
            await update.message.reply_text("Brak obserwowanych ofert.")
            return

        msg = f"\u2b50 <b>Obserwowane oferty ({len(deals)})</b>\n\n"
        for i, deal in enumerate(deals, 1):
            safe_title = html.escape(deal["title"][:80])
            price_str = f"{deal['price']:,} PLN".replace(",", " ") if deal["price"] else "brak ceny"
            link = html.escape(deal.get("link", ""))
            msg += f"{i}. <b>{safe_title}</b>\n"
            msg += f"   \U0001f4b0 {html.escape(price_str)}"
            if link:
                msg += f' | <a href="{link}">Link</a>'
            msg += "\n\n"

            if len(msg) > _MAX_MSG_LEN:
                msg += "... i więcej ofert"
                break

        await update.message.reply_text(msg, parse_mode="HTML", disable_web_page_preview=True)


_PERMANENT_MUTE_SENTINEL = "9999-12-31T00:00:00"


async def cmd_mute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/mute <deal_id> — permanent mute for a specific deal."""
    if not context.args:
        await update.message.reply_text("Użycie: /mute <deal_id>")
        return
    deal_id = context.args[0]
    with get_session() as session:
        ok = OfferRepository(session).set_muted_until(deal_id, _PERMANENT_MUTE_SENTINEL)
        if not ok:
            await update.message.reply_text(f"Nie znaleziono oferty: {html.escape(deal_id)}")
            return
        FeedbackRepository(session).record(deal_id, "mute")
    await update.message.reply_text(f"\U0001f515 Wyciszono ofertę {html.escape(deal_id)}")


async def cmd_snooze(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/snooze <deal_id> [days] — temporary mute (defaults to global default_snooze_days)."""
    if not context.args:
        await update.message.reply_text("Użycie: /snooze <deal_id> [dni]")
        return

    deal_id = context.args[0]
    if len(context.args) >= 2:
        try:
            days = int(context.args[1])
        except ValueError:
            await update.message.reply_text("Liczba dni musi być liczbą całkowitą.")
            return
        if days <= 0:
            await update.message.reply_text("Liczba dni musi być dodatnia.")
            return
    else:
        from deal_hunter.core.notification_config import load_global_config
        from deal_hunter.core.settings import get_settings

        cfg = load_global_config(get_settings().base_dir / "config" / "notifications.yaml")
        days = cfg.default_snooze_days

    until = (datetime.now() + timedelta(days=days)).isoformat()
    with get_session() as session:
        ok = OfferRepository(session).set_muted_until(deal_id, until)
        if not ok:
            await update.message.reply_text(f"Nie znaleziono oferty: {html.escape(deal_id)}")
            return
        FeedbackRepository(session).record(deal_id, "snooze")
    nice_date = datetime.fromisoformat(until).strftime("%d.%m.%Y")
    await update.message.reply_text(
        f"\U0001f4a4 Wyciszono ofertę {html.escape(deal_id)} do {nice_date}"
    )


async def cmd_unmute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/unmute <deal_id> — clear mute on a deal."""
    if not context.args:
        await update.message.reply_text("Użycie: /unmute <deal_id>")
        return
    deal_id = context.args[0]
    with get_session() as session:
        ok = OfferRepository(session).clear_muted_until(deal_id)
        if not ok:
            await update.message.reply_text(f"Nie znaleziono oferty: {html.escape(deal_id)}")
            return
        FeedbackRepository(session).record(deal_id, "unmute")
    await update.message.reply_text(f"\U0001f50a Włączono powiadomienia: {html.escape(deal_id)}")


async def cmd_muted(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/muted — list currently muted/snoozed deals."""
    with get_session() as session:
        deals = OfferRepository(session).get_muted(include_expired=False)

    if not deals:
        await update.message.reply_text("Brak wyciszonych ofert.")
        return

    lines = [f"\U0001f515 <b>Wyciszone oferty ({len(deals)})</b>\n"]
    for d in deals[:20]:
        until = d.get("muted_until") or ""
        if until.startswith("9999"):
            tag = "(stałe)"
        else:
            try:
                tag = "(do " + datetime.fromisoformat(until).strftime("%d.%m.%Y") + ")"
            except ValueError:
                tag = ""
        title = html.escape((d.get("title") or "")[:60])
        deal_id = html.escape(d.get("id") or "")
        lines.append(f"• <code>{deal_id}</code> — {title} {tag}")

    msg = "\n".join(lines)
    await update.message.reply_text(msg, parse_mode="HTML", disable_web_page_preview=True)
