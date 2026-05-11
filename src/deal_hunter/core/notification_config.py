"""Notification config — global YAML + per-profile resolution.

Global defaults live in `config/notifications.yaml` (auto-created on first
use). Each profile YAML may override `cooldown_days` and
`alert_through_cooldown_if_ath_low` inside its `price_tracking` block.

`default_snooze_days` is global-only — it's a UI default, not an alerting
rule, so per-profile override would be confusing without value.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

DEFAULT_COOLDOWN_DAYS = 7
DEFAULT_ALERT_THROUGH_COOLDOWN_IF_ATH_LOW = True
DEFAULT_DEFAULT_SNOOZE_DAYS = 30

_YAML_BLOCK = "price_drop_alerts"


@dataclass(frozen=True)
class NotificationConfig:
    cooldown_days: int
    alert_through_cooldown_if_ath_low: bool
    default_snooze_days: int


def _defaults() -> NotificationConfig:
    return NotificationConfig(
        cooldown_days=DEFAULT_COOLDOWN_DAYS,
        alert_through_cooldown_if_ath_low=DEFAULT_ALERT_THROUGH_COOLDOWN_IF_ATH_LOW,
        default_snooze_days=DEFAULT_DEFAULT_SNOOZE_DAYS,
    )


def load_global_config(path: Path) -> NotificationConfig:
    """Read the global YAML; missing or malformed → hardcoded defaults."""
    if not path.exists():
        return _defaults()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError) as exc:
        logger.warning("Failed to parse %s, using defaults: %s", path, exc)
        return _defaults()
    if not isinstance(raw, dict):
        return _defaults()
    block = raw.get(_YAML_BLOCK)
    if not isinstance(block, dict):
        return _defaults()
    defaults = _defaults()
    return NotificationConfig(
        cooldown_days=_int_or(block.get("cooldown_days"), defaults.cooldown_days),
        alert_through_cooldown_if_ath_low=_bool_or(
            block.get("alert_through_cooldown_if_ath_low"),
            defaults.alert_through_cooldown_if_ath_low,
        ),
        default_snooze_days=_int_or(block.get("default_snooze_days"), defaults.default_snooze_days),
    )


def save_global_config(path: Path, cfg: NotificationConfig) -> None:
    """Atomic write — temp + rename so a crash mid-write doesn't corrupt the file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = {
        _YAML_BLOCK: {
            "cooldown_days": cfg.cooldown_days,
            "alert_through_cooldown_if_ath_low": cfg.alert_through_cooldown_if_ath_low,
            "default_snooze_days": cfg.default_snooze_days,
        }
    }
    tmp.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    tmp.replace(path)


def resolve_for_profile(global_cfg: NotificationConfig, profile: dict) -> NotificationConfig:
    """Apply per-profile `price_tracking` overrides on top of global config."""
    pt = profile.get("price_tracking", {}) or {}
    cooldown = pt.get("cooldown_days")
    ath = pt.get("alert_through_cooldown_if_ath_low")
    return NotificationConfig(
        cooldown_days=cooldown if cooldown is not None else global_cfg.cooldown_days,
        alert_through_cooldown_if_ath_low=(
            ath if ath is not None else global_cfg.alert_through_cooldown_if_ath_low
        ),
        default_snooze_days=global_cfg.default_snooze_days,
    )


def _int_or(value: object, fallback: int) -> int:
    if isinstance(value, bool):  # bool is subclass of int — refuse it explicitly
        return fallback
    if isinstance(value, int):
        return value
    return fallback


def _bool_or(value: object, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    return fallback
