"""Notifications settings page + per-deal mute APIs."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import ValidationError
from sqlalchemy.orm import Session

from deal_hunter.api import templates
from deal_hunter.api.dependencies import get_db
from deal_hunter.api.schemas import GlobalNotificationConfig, MuteRequest
from deal_hunter.core.notification_config import (
    NotificationConfig,
    load_global_config,
    save_global_config,
)
from deal_hunter.core.settings import get_settings
from deal_hunter.storage.repositories import OfferRepository

PERMANENT_MUTE_SENTINEL = "9999-12-31T00:00:00"

router = APIRouter()


def _global_config_path() -> Path:
    return get_settings().base_dir / "config" / "notifications.yaml"


@router.get("/notifications", response_class=HTMLResponse)
def notifications_page(request: Request) -> HTMLResponse:
    cfg = load_global_config(_global_config_path())
    return templates.TemplateResponse(
        request,
        "notifications.html",
        {"config": cfg},
    )


@router.post("/api/notifications/global")
def api_notifications_global(
    cooldown_days: str = Form(...),
    alert_through_cooldown_if_ath_low: str = Form(""),
    default_snooze_days: str = Form(...),
) -> Response:
    ath_raw = (alert_through_cooldown_if_ath_low or "").strip().lower()
    ath = ath_raw in {"true", "1", "on", "yes"}
    try:
        validated = GlobalNotificationConfig(
            cooldown_days=int(cooldown_days),
            alert_through_cooldown_if_ath_low=ath,
            default_snooze_days=int(default_snooze_days),
        )
    except (ValueError, ValidationError) as exc:
        return JSONResponse(
            {"error": str(exc)},
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    save_global_config(
        _global_config_path(),
        NotificationConfig(
            cooldown_days=validated.cooldown_days,
            alert_through_cooldown_if_ath_low=validated.alert_through_cooldown_if_ath_low,
            default_snooze_days=validated.default_snooze_days,
        ),
    )
    return JSONResponse({"ok": True})


@router.post("/api/deals/{deal_id}/mute")
def api_deal_mute(
    deal_id: str,
    days: str = Form(""),
    session: Session = Depends(get_db),
) -> Response:
    days_clean = days.strip()
    parsed_days: int | None
    if not days_clean:
        parsed_days = None
    else:
        try:
            parsed_days = int(days_clean)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="days must be an integer") from exc
        try:
            MuteRequest(days=parsed_days)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    if parsed_days is None:
        until = PERMANENT_MUTE_SENTINEL
    else:
        until = (datetime.now() + timedelta(days=parsed_days)).isoformat()

    ok = OfferRepository(session).set_muted_until(deal_id, until)
    if not ok:
        raise HTTPException(status_code=404, detail="Deal not found")
    return JSONResponse({"ok": True, "muted_until": until})


@router.post("/api/deals/{deal_id}/unmute")
def api_deal_unmute(
    deal_id: str,
    session: Session = Depends(get_db),
) -> Response:
    ok = OfferRepository(session).clear_muted_until(deal_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Deal not found")
    return JSONResponse({"ok": True})
