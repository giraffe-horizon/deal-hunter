"""Tests for should_send_price_drop — pure decision logic."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

from deal_hunter.core.notification_config import NotificationConfig
from deal_hunter.services.notification_filter import should_send_price_drop


def _cfg(cooldown=7, ath=True, snooze=30):
    return NotificationConfig(
        cooldown_days=cooldown,
        alert_through_cooldown_if_ath_low=ath,
        default_snooze_days=snooze,
    )


def _mock_repos(muted_until=None, last_sent=None):
    deal_repo = MagicMock()
    deal_repo.get_by_id.return_value = (
        {"muted_until": muted_until} if muted_until is not None else {"muted_until": None}
    )
    alert_repo = MagicMock()
    alert_repo.last_price_drop_sent_at.return_value = last_sent
    return deal_repo, alert_repo


def test_allows_when_never_alerted_and_not_muted():
    deal_repo, alert_repo = _mock_repos()
    allow, reason = should_send_price_drop(
        deal_id="pepper:1",
        profile_name="bikes",
        is_all_time_low=False,
        config=_cfg(),
        deal_repo=deal_repo,
        alert_repo=alert_repo,
        now=datetime(2026, 5, 11, 10, 0, 0),
    )
    assert allow is True
    assert reason == "ok"


def test_blocks_when_muted_permanently():
    deal_repo, alert_repo = _mock_repos(muted_until="9999-12-31T00:00:00")
    allow, reason = should_send_price_drop(
        deal_id="pepper:1",
        profile_name="bikes",
        is_all_time_low=True,  # ATH override does NOT bypass mute.
        config=_cfg(),
        deal_repo=deal_repo,
        alert_repo=alert_repo,
        now=datetime(2026, 5, 11, 10, 0, 0),
    )
    assert allow is False
    assert reason.startswith("muted_until=")


def test_blocks_when_snoozed_until_future():
    deal_repo, alert_repo = _mock_repos(muted_until="2026-06-01T00:00:00")
    allow, reason = should_send_price_drop(
        deal_id="pepper:1",
        profile_name="bikes",
        is_all_time_low=False,
        config=_cfg(),
        deal_repo=deal_repo,
        alert_repo=alert_repo,
        now=datetime(2026, 5, 11, 10, 0, 0),
    )
    assert allow is False
    assert reason.startswith("muted_until=")


def test_expired_snooze_treated_as_unmuted():
    deal_repo, alert_repo = _mock_repos(muted_until="2026-01-01T00:00:00")
    allow, reason = should_send_price_drop(
        deal_id="pepper:1",
        profile_name="bikes",
        is_all_time_low=False,
        config=_cfg(),
        deal_repo=deal_repo,
        alert_repo=alert_repo,
        now=datetime(2026, 5, 11, 10, 0, 0),
    )
    assert allow is True
    assert reason == "ok"


def test_blocks_within_cooldown_window():
    now = datetime(2026, 5, 11, 10, 0, 0)
    last_sent = (now - timedelta(days=3)).isoformat()
    deal_repo, alert_repo = _mock_repos(last_sent=last_sent)
    allow, reason = should_send_price_drop(
        deal_id="pepper:1",
        profile_name="bikes",
        is_all_time_low=False,
        config=_cfg(cooldown=7),
        deal_repo=deal_repo,
        alert_repo=alert_repo,
        now=now,
    )
    assert allow is False
    assert reason.startswith("cooldown:")


def test_ath_override_bypasses_cooldown():
    now = datetime(2026, 5, 11, 10, 0, 0)
    last_sent = (now - timedelta(days=3)).isoformat()
    deal_repo, alert_repo = _mock_repos(last_sent=last_sent)
    allow, reason = should_send_price_drop(
        deal_id="pepper:1",
        profile_name="bikes",
        is_all_time_low=True,
        config=_cfg(cooldown=7, ath=True),
        deal_repo=deal_repo,
        alert_repo=alert_repo,
        now=now,
    )
    assert allow is True
    assert reason == "ath_override"


def test_ath_override_disabled_still_blocks_in_cooldown():
    now = datetime(2026, 5, 11, 10, 0, 0)
    last_sent = (now - timedelta(days=3)).isoformat()
    deal_repo, alert_repo = _mock_repos(last_sent=last_sent)
    allow, reason = should_send_price_drop(
        deal_id="pepper:1",
        profile_name="bikes",
        is_all_time_low=True,
        config=_cfg(cooldown=7, ath=False),
        deal_repo=deal_repo,
        alert_repo=alert_repo,
        now=now,
    )
    assert allow is False
    assert reason.startswith("cooldown:")


def test_cooldown_zero_means_no_cooldown():
    now = datetime(2026, 5, 11, 10, 0, 0)
    last_sent = (now - timedelta(minutes=1)).isoformat()
    deal_repo, alert_repo = _mock_repos(last_sent=last_sent)
    allow, _ = should_send_price_drop(
        deal_id="pepper:1",
        profile_name="bikes",
        is_all_time_low=False,
        config=_cfg(cooldown=0),
        deal_repo=deal_repo,
        alert_repo=alert_repo,
        now=now,
    )
    assert allow is True


def test_cooldown_just_expired_allows():
    now = datetime(2026, 5, 11, 10, 0, 0)
    last_sent = (now - timedelta(days=7, seconds=1)).isoformat()
    deal_repo, alert_repo = _mock_repos(last_sent=last_sent)
    allow, _ = should_send_price_drop(
        deal_id="pepper:1",
        profile_name="bikes",
        is_all_time_low=False,
        config=_cfg(cooldown=7),
        deal_repo=deal_repo,
        alert_repo=alert_repo,
        now=now,
    )
    assert allow is True


def test_handles_missing_offer_gracefully():
    """If the offer doesn't exist yet (first time seeing it), there's nothing to mute."""
    deal_repo = MagicMock()
    deal_repo.get_by_id.return_value = None
    alert_repo = MagicMock()
    alert_repo.last_price_drop_sent_at.return_value = None
    allow, reason = should_send_price_drop(
        deal_id="pepper:1",
        profile_name="bikes",
        is_all_time_low=False,
        config=_cfg(),
        deal_repo=deal_repo,
        alert_repo=alert_repo,
        now=datetime(2026, 5, 11, 10, 0, 0),
    )
    assert allow is True
    assert reason == "ok"
