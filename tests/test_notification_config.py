"""Tests for NotificationConfig — global YAML + per-profile resolution."""

import yaml

from deal_hunter.core.notification_config import (
    DEFAULT_ALERT_THROUGH_COOLDOWN_IF_ATH_LOW,
    DEFAULT_COOLDOWN_DAYS,
    DEFAULT_DEFAULT_SNOOZE_DAYS,
    NotificationConfig,
    load_global_config,
    resolve_for_profile,
    save_global_config,
)


def test_load_global_missing_file_returns_hardcoded_defaults(tmp_path):
    cfg = load_global_config(tmp_path / "notifications.yaml")
    assert cfg.cooldown_days == DEFAULT_COOLDOWN_DAYS
    assert cfg.default_snooze_days == DEFAULT_DEFAULT_SNOOZE_DAYS
    assert cfg.alert_through_cooldown_if_ath_low == DEFAULT_ALERT_THROUGH_COOLDOWN_IF_ATH_LOW


def test_load_global_reads_existing_yaml(tmp_path):
    path = tmp_path / "notifications.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "price_drop_alerts": {
                    "cooldown_days": 14,
                    "alert_through_cooldown_if_ath_low": False,
                    "default_snooze_days": 7,
                }
            }
        )
    )
    cfg = load_global_config(path)
    assert cfg.cooldown_days == 14
    assert cfg.default_snooze_days == 7
    assert cfg.alert_through_cooldown_if_ath_low is False


def test_load_global_malformed_yaml_returns_defaults(tmp_path):
    path = tmp_path / "notifications.yaml"
    path.write_text("not: valid: yaml: at: all: [")
    cfg = load_global_config(path)
    assert cfg.cooldown_days == DEFAULT_COOLDOWN_DAYS


def test_load_global_partial_yaml_fills_in_defaults(tmp_path):
    path = tmp_path / "notifications.yaml"
    path.write_text(yaml.safe_dump({"price_drop_alerts": {"cooldown_days": 21}}))
    cfg = load_global_config(path)
    assert cfg.cooldown_days == 21
    assert cfg.default_snooze_days == DEFAULT_DEFAULT_SNOOZE_DAYS
    assert cfg.alert_through_cooldown_if_ath_low == DEFAULT_ALERT_THROUGH_COOLDOWN_IF_ATH_LOW


def test_resolve_for_profile_uses_profile_when_present():
    global_cfg = NotificationConfig(
        cooldown_days=7,
        alert_through_cooldown_if_ath_low=True,
        default_snooze_days=30,
    )
    profile = {
        "price_tracking": {
            "cooldown_days": 14,
            "alert_through_cooldown_if_ath_low": False,
        }
    }
    resolved = resolve_for_profile(global_cfg, profile)
    assert resolved.cooldown_days == 14
    assert resolved.alert_through_cooldown_if_ath_low is False
    # Snooze is global-only.
    assert resolved.default_snooze_days == 30


def test_resolve_for_profile_falls_back_to_global():
    global_cfg = NotificationConfig(
        cooldown_days=7,
        alert_through_cooldown_if_ath_low=True,
        default_snooze_days=30,
    )
    resolved = resolve_for_profile(global_cfg, {})
    assert resolved.cooldown_days == 7
    assert resolved.alert_through_cooldown_if_ath_low is True


def test_resolve_for_profile_zero_is_valid_override():
    """cooldown_days=0 must be honored (means: no cooldown)."""
    global_cfg = NotificationConfig(
        cooldown_days=7,
        alert_through_cooldown_if_ath_low=True,
        default_snooze_days=30,
    )
    resolved = resolve_for_profile(global_cfg, {"price_tracking": {"cooldown_days": 0}})
    assert resolved.cooldown_days == 0


def test_save_global_config_writes_atomically(tmp_path):
    path = tmp_path / "notifications.yaml"
    cfg = NotificationConfig(
        cooldown_days=10,
        alert_through_cooldown_if_ath_low=False,
        default_snooze_days=45,
    )
    save_global_config(path, cfg)
    assert path.exists()
    data = yaml.safe_load(path.read_text())
    block = data["price_drop_alerts"]
    assert block["cooldown_days"] == 10
    assert block["alert_through_cooldown_if_ath_low"] is False
    assert block["default_snooze_days"] == 45
    # Roundtrip
    cfg2 = load_global_config(path)
    assert cfg2 == cfg


def test_save_global_config_does_not_leave_tmp_file(tmp_path):
    path = tmp_path / "notifications.yaml"
    save_global_config(
        path,
        NotificationConfig(
            cooldown_days=1,
            alert_through_cooldown_if_ath_low=True,
            default_snooze_days=1,
        ),
    )
    assert not any(p.name.endswith(".tmp") for p in tmp_path.iterdir())
