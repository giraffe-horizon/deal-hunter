# Notification Management Settings

**Status:** approved, ready for plan
**Date:** 2026-05-11

## Goal

Reduce price-drop alert noise by giving the user control over alert cadence and per-deal silencing. The user is overwhelmed by low-value drop alerts on the same deals.

This spec adds:

1. A per-profile **cooldown** that suppresses repeat price-drop alerts for the same deal for N days, with an opt-in "alert through cooldown on new all-time low" override.
2. Per-deal **mute** (permanent) and **snooze** (temporary) controls accessible from Telegram inline buttons, bot commands, and the dashboard.
3. **Global defaults** for cooldown / snooze that any profile YAML can override, mirroring the existing `QUIET_HOURS_*` pattern.
4. A new dashboard page `/notifications` for editing global defaults, plus per-deal mute controls integrated into the existing deals/watchlist views.

Non-goals (deliberately out of scope):

- AND-combined thresholds, minimum-final-price filters, escalation rules, daily digest opt-in. These were considered and dropped — the cooldown + mute combination is sufficient for the stated problem and any of them can be added later without rework.
- Per-deal cooldown overrides. Cooldown is per profile; muting is per deal. Two concepts, two surfaces — no third.

## Decisions

| Question | Answer |
|---|---|
| Filter dimension? | Per-deal cooldown (N days of silence per deal after an alert). |
| Cooldown override? | Alert through cooldown if the new price is a new all-time low. Toggleable, default on. |
| Per-deal controls? | Both permanent mute and temporary snooze (default 30 days). |
| Global vs per-profile? | Global defaults; per-profile YAML can override. Same precedence as `QUIET_HOURS_START`/`END` today. |
| Skip vs Mute? | Keep both. Skip = `status='rejected'`, hides from dashboard. Mute = stop alerting; deal stays visible. They serve different intents. |
| Mute storage shape? | Single `muted_until` column on `offers`. NULL = not muted; future timestamp = snoozed; sentinel `MAX_DATETIME` = permanent. One column, one comparison. |
| Cooldown storage? | Derived from `alert_queue` (`MAX(sent_at) WHERE deal_id=? AND alert_type='price_drop'`). No new column needed, assuming `alert_queue` has `deal_id`; migration adds it if not. |
| Suppressed alerts behavior? | Dropped, not queued. Cooldown is "skip," not "delay." Logged at INFO with reason for tuning. |
| Global config location? | New file `config/notifications.yaml`. Not `.env` — these aren't secrets and the shape is structured. Auto-created on first run with hardcoded defaults written out. |

## Configuration Model

### Layer 1 — Global defaults (`config/notifications.yaml`)

```yaml
price_drop_alerts:
  cooldown_days: 7
  alert_through_cooldown_if_ath_low: true
  default_snooze_days: 30
```

Created on first startup if missing. Editable via the dashboard `/notifications` page or by hand.

### Layer 2 — Per-profile override

Existing `price_tracking` block in any `profiles/*.yaml` gains optional fields:

```yaml
price_tracking:
  enabled: true
  min_drop_percent: 15
  min_drop_amount: 200
  track_increases: false
  cooldown_days: 14                            # overrides global
  alert_through_cooldown_if_ath_low: false     # overrides global
```

### Resolution

At profile load time:

1. Field present on profile → use it.
2. Else field present in `config/notifications.yaml` → use it.
3. Else hardcoded fallback: `cooldown_days=7`, `alert_through_cooldown_if_ath_low=true`, `default_snooze_days=30`.

The merged result is held in `PriceTrackingConfig` (extended) and a sibling `NotificationConfig` dataclass for the snooze field (which only makes sense globally, not per-profile).

`default_snooze_days` is global-only — it controls what the Telegram "Drzemka 30d" button sets, and isn't profile-scoped because it's a UI default, not an alerting rule.

## Data Model

### Migration `003_notification_settings.py`

1. `ALTER TABLE offers ADD COLUMN muted_until DATETIME NULL` + index on `muted_until`.
2. **Conditional**: if `alert_queue.deal_id` doesn't exist as a top-level column (survey indicates it may live inside `payload`):
   - Add `alert_queue.deal_id TEXT NULL` + index.
   - Backfill from `payload` JSON in one UPDATE pass.
3. Down-migration drops both additions.

Existing migrations: `001_baseline`, `002_seen_deals`. This is `003`.

### `Offer.muted_until` semantics

| Value | Meaning |
|---|---|
| `NULL` | Not muted; alerts proceed normally. (Default for all rows.) |
| Future datetime | Snoozed until that timestamp. Alerts suppressed. |
| `datetime(9999, 12, 31)` (`MAX_DATETIME`) | Permanent mute. |
| Past datetime | Expired snooze. Treated as NULL by filter. (A cleanup job is unnecessary — the filter handles it.) |

Filter SQL: `WHERE muted_until IS NULL OR muted_until <= NOW()` to find sendable deals.

### No new column for cooldown

Existing `alert_queue` rows with `sent_at IS NOT NULL` and `alert_type='price_drop'` are the source of truth. The notification filter queries `MAX(sent_at)` for the deal and compares against `now - cooldown_days`.

## Alert Filter Pipeline

### New module: `services/notification_filter.py`

One public function:

```python
def should_send_price_drop(
    deal_id: str,
    profile_name: str,
    is_all_time_low: bool,
    config: NotificationConfig,
    deal_repo: DealRepository,
    alert_repo: AlertQueueRepository,
    now: datetime | None = None,    # injectable for tests
) -> tuple[bool, str]:
    """Returns (allow, reason)."""
```

### Decision order

1. **Mute check**: `Offer.muted_until` is set and `> now` → `(False, "muted_until=<iso>")`.
2. **Cooldown check**: last `price_drop` `sent_at` for this deal is within `cooldown_days`:
   - If `alert_through_cooldown_if_ath_low` AND `is_all_time_low` → `(True, "ath_override")`.
   - Else → `(False, "cooldown:<N>d_remaining")`.
3. **Default**: `(True, "ok")`.

### Wiring in `services/alerter.py`

In the existing price-drop dispatch loop (today in `AlertService.send_price_drop_alerts` or equivalent):

```python
for change in price_changes:
    allow, reason = should_send_price_drop(...)
    logger.info("price_drop_filter deal=%s allow=%s reason=%s",
                change.deal.id, allow, reason)
    if not allow:
        continue
    # existing dispatch / queue logic
```

The filter runs **before** quiet-hours queuing. A muted deal does not enter `alert_queue`. Quiet-hours queuing is unchanged for deals that pass the filter.

### `is_all_time_low` source

`PriceChange.is_lowest_ever` already exists on `services/price_tracker.py` outputs. Pass it through to the filter.

## Telegram UX

### Inline keyboard (`notifiers/telegram/transport.py`, `build_deal_keyboard`)

Today:
```
[Otwórz] [Obserwuj] [Skip]
```

New:
```
[Otwórz] [Obserwuj] [Skip]            ← unchanged
[💤 Drzemka 30d] [🔕 Wycisz]          ← new
```

The "30d" label reflects the current `default_snooze_days` value at message-build time (so users see what the button will actually do).

### Callbacks

- `snooze:<deal_id>` → `OfferRepository.set_muted_until(deal_id, now + default_snooze_days)`. Toast: `💤 Wyciszono do <DD.MM.YYYY>`.
- `mute:<deal_id>` → `OfferRepository.set_muted_until(deal_id, MAX_DATETIME)`. Toast: `🔕 Wyciszono`.

Existing callbacks (`watch:`, `skip:`) unchanged.

### Bot commands (`bot/commands.py`)

- `/mute <deal_id>` — permanent.
- `/snooze <deal_id> [days]` — `days` defaults to global `default_snooze_days`.
- `/unmute <deal_id>` — clears `muted_until`.
- `/muted` — lists currently muted/snoozed deals (id, short title, expires-at or "permanent").

Polish UI strings on toasts/responses; English in code, comments, logs (per project convention).

## Dashboard UX

### New page: `/notifications`

Server-rendered Jinja2 template + small HTMX form. Sidebar link added.

Form fields (Pydantic-validated, mirrors existing profile-edit pattern):

| Field | Type | Range |
|---|---|---|
| `cooldown_days` | int | 0–90 |
| `alert_through_cooldown_if_ath_low` | bool (checkbox) | — |
| `default_snooze_days` | int | 1–365 |

Save POSTs to `/api/notifications/global`, which writes `config/notifications.yaml` atomically (write-tmp + rename) and triggers config reload.

### Per-deal mute controls — `/deals` and `/watchlist`

Each row gains:

- Status badge next to title when muted: `🔕 Wyciszono` or `💤 Drzemka (do 11.06.2026)`.
- Action buttons: `🔕 Mute` / `Unmute` (toggles permanent); `💤 Snooze` (with optional days selector — default uses global).
- HTMX in-place update — no full page reload on toggle.

### New filter chip on `/watchlist`

The page today filters by `status='watching'`. Add a `Wyciszone` chip that shows all currently-muted deals (regardless of status). Mutually exclusive with the existing chips.

### Profile-edit form

Existing form already exposes `price_tracking`. Add optional `cooldown_days` and `alert_through_cooldown_if_ath_low` fields with helper text:

> Pozostaw puste, aby użyć globalnego ustawienia (`{global_value}`).

Empty input → field not written to YAML → falls back to global at resolution time.

### New API endpoints

| Method | Path | Body | Purpose |
|---|---|---|---|
| GET | `/api/notifications/global` | — | Returns current global config. |
| POST | `/api/notifications/global` | `{cooldown_days, alert_through_cooldown_if_ath_low, default_snooze_days}` | Writes `config/notifications.yaml`. |
| POST | `/api/deals/{deal_id}/mute` | `{"days": int \| null}` | `null` = permanent; integer = snooze N days. |
| POST | `/api/deals/{deal_id}/unmute` | — | Clears `muted_until`. |

Pydantic schemas live in `dashboard/schemas.py` alongside existing ones.

### New repository methods (`OfferRepository`)

- `set_muted_until(deal_id: str, until: datetime | None) -> bool`
- `get_muted(include_expired: bool = False) -> list[Offer]`

## Rollout Order

Single PR, solo-dev project. Build order:

1. Migration `003_notification_settings.py` + model field on `Offer`.
2. Config loader, `NotificationConfig` dataclass, `PriceTrackingConfig` extension, fallback chain.
3. `services/notification_filter.py` + unit tests.
4. Alerter integration (filter call before queue) + integration tests.
5. `OfferRepository.set_muted_until` / `get_muted` + repo tests.
6. Telegram callbacks (`mute:`, `snooze:`) + bot commands + bot tests.
7. Dashboard `/notifications` page, API endpoints, per-deal buttons on `/deals` and `/watchlist`, profile-edit field, dashboard tests.
8. Logging review — verify `INFO` logs from the filter give the user enough to tune `cooldown_days`.

Backward compat: existing profiles work unchanged. `muted_until` defaults to NULL. Profiles without `cooldown_days` inherit the global. Existing alerts continue to dispatch with the same behavior on day 1 (default cooldown is 7d; first alert per deal always goes through).

## Testing

| Module | New / Extended | Coverage |
|---|---|---|
| `tests/test_notification_filter.py` | new | Pure-function tests of `should_send_price_drop`: cooldown expiry math, mute-until comparison (past/future/MAX_DATETIME/NULL), ATH override toggle on/off, deal never alerted before, `cooldown_days=0`. |
| `tests/test_notification_config.py` | new | Resolution chain: global only, profile overrides global, missing file, malformed YAML, hardcoded fallback, atomic write. |
| `tests/test_repositories.py` | extended | `set_muted_until` (set/clear/sentinel), `get_muted` with and without expired. |
| `tests/test_feedback_bot.py` | extended | `mute:` / `snooze:` callbacks, `/mute` `/snooze` `/unmute` `/muted` commands. |
| `tests/test_services.py` (or new `test_alerter_filter.py`) | extended | Integration: muted deal doesn't enter `alert_queue`; cooldown applied across two consecutive `send_price_drop_alerts` calls; ATH override fires through cooldown. |
| `tests/test_dashboard.py` | extended | `/notifications` GET/POST round-trip, mute/unmute API endpoints, watchlist `Wyciszone` filter, profile-edit accepts and persists optional cooldown fields. |

TDD per `superpowers:test-driven-development` skill — test-first for the filter and config loader (pure logic); test-first or test-after for UI glue as appropriate.

## Open Items for Plan Stage

- **Verify `alert_queue` schema**: confirm whether `deal_id` is a top-level column or inside `payload`. Survey indicated `(profile, alert_type, payload, sent_at)` only. The migration must add the column + backfill if so.
- **Verify cooldown source**: confirm `alert_queue.sent_at` is set at dispatch time, not enqueue time. If only enqueue is recorded, the filter should query a different signal (e.g., a `dispatched_at`) — adjust during implementation.
- **MAX_DATETIME constant**: SQLite stores datetimes as ISO strings; verify the sentinel comparison works as expected with the existing SQLAlchemy column type and locale settings.
