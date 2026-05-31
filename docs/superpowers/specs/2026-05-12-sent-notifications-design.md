# Sent Notifications — Persist Every Telegram Send

**Status:** approved, ready for plan
**Date:** 2026-05-12

## Goal

Record every successful Telegram send into a new SQLite table, expose a dashboard view to browse the history, and re-point the per-deal cooldown query at the new table.

Two value drivers:

1. **Fix the cooldown bug.** The notification-management feature (`2026-05-11-notification-management-design.md`, PR #17) routes `last_price_drop_sent_at` through `alert_queue`. That table only ever receives rows during quiet-hours queueing — every direct send skips it. As-shipped, the cooldown effectively never fires unless the user happens to be in quiet hours.
2. **Browseable audit trail.** A new `/notifications/history` page in the dashboard lists what was sent, when, to whom, for which deal.

Non-goals (out of scope on purpose):

- Capturing Telegram's `message_id` from API responses. Not needed for cooldown or history; can be added later via a one-column migration without rework.
- A `status` column distinguishing sent vs failed. Failures stay in the application log; storing them would double row writes and complicate the cooldown query for no concrete user need.
- Retention / cleanup policy. SQLite handles millions of rows; we add a cron job later if the table actually grows large.
- Recording at the private `_send_message` / `_send_photo` layer. Each public `send_*` method owns its alert-type and payload shape.

## Decisions

| Question | Answer |
|---|---|
| What gets recorded? | All seven public Telegram senders (deal, price_drop, summary, watchlist, digest, source_failure, chart). |
| Reuse `alert_queue` or new table? | New `sent_notifications` table. `alert_queue` keeps its queue semantics. |
| When does the record happen? | After the HTTP call returns successfully. A failing send leaves no row. |
| Transactional with the send? | No — fire-and-forget. A DB blip logs `WARNING` but does not bubble up. |
| Cooldown query source? | New table. `AlertQueueRepository.last_price_drop_sent_at` deleted; replaced by `SentNotificationRepository.last_sent_at(deal_id, alert_type)`. |
| Migration backfill? | None. First post-deploy run has no cooldown history; eligible drops alert immediately. Acceptable one-shot reset. |
| FK constraint on `deal_id` → `offers.id`? | No. Soft reference so history survives offer cleanup or profile rename. |
| Dashboard view? | New `/notifications/history` page with type + profile + date filters, paginated. Sub-nav with `/notifications` (settings vs history). |
| Capture Telegram `message_id`? | No (YAGNI). |
| Record failed sends? | No (YAGNI; logs cover audit). |

## Data Model

### Migration `007_sent_notifications.py`

Additive only — no backfill.

1. `CREATE TABLE sent_notifications` with the columns below.
2. `CREATE INDEX ix_sent_notifications_deal_id_alert_type ON sent_notifications(deal_id, alert_type, sent_at)`.
3. `CREATE INDEX ix_sent_notifications_sent_at ON sent_notifications(sent_at)`.
4. Down-migration drops both indexes then the table.

### `sent_notifications` columns

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | INTEGER | NO | PK, autoincrement |
| `alert_type` | TEXT | NO | One of `deal`, `price_drop`, `summary`, `watchlist`, `digest`, `source_failure`, `chart` |
| `deal_id` | TEXT | YES | Soft reference to `offers.id`; NULL for digest / source_failure / standalone charts |
| `profile` | TEXT | YES | NULL for digest / source_failure / cross-profile messages |
| `payload` | TEXT | NO | JSON-serialised — same blob shape used in `alert_queue.payload` today so flush code can reuse it |
| `sent_at` | TEXT | NO | ISO datetime stamped at insert |

### Index rationale

- `(deal_id, alert_type, sent_at)` is the exact key for the cooldown query (`MAX(sent_at) WHERE deal_id = ? AND alert_type = 'price_drop'`). Leading column matches the WHERE clause; trailing `sent_at` lets SQLite resolve `MAX` from the index without a row visit.
- `(sent_at)` powers the dashboard history page (`ORDER BY sent_at DESC LIMIT 50`).

## Recording Hook

### New module `src/deal_hunter/notifiers/telegram/recorder.py`

```python
def record_sent_notification(
    *,
    alert_type: str,
    payload: dict,
    deal_id: str | None = None,
    profile: str | None = None,
    session_factory: Callable[[], AbstractContextManager[Session]] = get_session,
) -> None:
    """Insert a row into sent_notifications. Fire-and-forget; logs and swallows DB errors."""
```

- Builds a fresh session via `get_session` (the project's existing context manager).
- Inserts via `SentNotificationRepository.record`.
- Catches `sqlalchemy.exc.SQLAlchemyError` and logs at `WARNING`.
- Re-raises nothing — a DB blip must not fail an otherwise-successful Telegram send.
- `session_factory` is an injection point for tests; production callers omit it.

### Why a fresh session, not a passed-in one

`TelegramNotifier` is built once with bot token + chat id and used across many hunts. Threading a session through every `send_*` call would entangle HTTP I/O with the per-hunt transactional boundary it shouldn't own. The recorder gets its own short-lived session.

### Public Telegram methods affected

Each `send_*` method in `notifiers/telegram/transport.py` receives new optional kwargs `profile` and (where missing) `alert_type` from its caller, calls `_send_message` / `_send_photo` as today, and on a non-exceptional return calls `record_sent_notification(...)` with this shape:

| Method | alert_type | deal_id | profile | payload |
|---|---|---|---|---|
| `send_alert` | `"deal"` | `deal.id` | from caller (new kwarg) | `{title, price, link, score, plus, minus}` |
| `send_price_drop_alert` | `"price_drop"` | `deal.id` | from caller | `{title, link, old_price, new_price, diff_pln, diff_percent, is_lowest_ever}` |
| `send_summary` | `"summary"` | `None` | from caller | `{remaining_count, sample_titles[:5]}` |
| `send_watchlist_alert` | `"watchlist"` | `deal.id` | from caller | `{title, target_price, current_price}` |
| `send_digest` | `"digest"` | `None` | `None` | `{drop_count, top_drops[:10]}` |
| `send_photo` (used for charts) | `"chart"` | from caller (new kwarg) | from caller | `{caption}` |
| `send_text` (used by `send_source_failure_alert` + queue flush) | from caller | from caller | from caller | `{text_preview: text[:200]}` |

**`send_source_failure_alert`** calls `send_text` directly; the recording line is added in `services/alerter.py` right after the `send_text` call, with `alert_type="source_failure"`, `deal_id=None`, `profile=None`.

**Queue-flush path** in `alerter.flush_queued` already knows `alert_type` and `deal_id` from each `alert_queue` row — it calls `record_sent_notification` with those after each successful `send_text`. Effectively, a quiet-hours-queued alert produces exactly one `sent_notifications` row, written at flush time.

### Caller plumbing

`AlertService` knows `profile_name` for every dispatch path. It threads it through as a new kwarg to each `send_*` call. Where `alert_type` is already implicit in the method (e.g. `send_price_drop_alert`), the method itself fills it in; for generic `send_text` / `send_photo` callers pass it explicitly.

## Cooldown Query Switch

### New `SentNotificationRepository.last_sent_at`

```python
def last_sent_at(self, deal_id: str, alert_type: str) -> str | None:
    """MAX(sent_at) for the given deal + alert_type, or None if no rows."""
```

Generalised from the existing `last_price_drop_sent_at` — works for any alert type.

### Filter rewire

`services/notification_filter.should_send_price_drop`:

- Old: `alert_repo: AlertQueueRepository` → `alert_repo.last_price_drop_sent_at(deal_id)`.
- New: `sent_repo: SentNotificationRepository` → `sent_repo.last_sent_at(deal_id, "price_drop")`.

Function signature changes: `alert_repo` parameter is renamed to `sent_repo` and its type changes. All ten existing tests in `test_notification_filter.py` are mock-based and only need the parameter rename + a one-line change to the helper that builds the mock.

### Caller rewire

`AlertService.__init__` gains a `sent_repo: SentNotificationRepository | None = None` parameter alongside `offer_repo`. `services/hunt_service.run_profile` constructs `sent_repo = SentNotificationRepository(session)` next to the other repos and threads it in. The filter call inside `AlertService.send_price_drop_alerts` passes `sent_repo` instead of `alert_repo`.

### Removed code

`AlertQueueRepository.last_price_drop_sent_at` is **deleted**. It was added in PR #17 and has exactly one caller (the filter). Cleaner than leaving a deprecated method.

### Behaviour on first deploy

`sent_notifications` is empty after migration 007. The first hunt sees `last_sent_at(...) → None` for every deal → cooldown never fires that run → every eligible drop alerts. From the second hunt onward, cooldown behaves normally.

If this matters operationally, the migration could backfill from `alert_queue` (`INSERT INTO sent_notifications ... SELECT ... FROM alert_queue WHERE sent_at IS NOT NULL`). The current decision is **not** to backfill — `alert_queue` only ever held quiet-hours-flushed rows, which is a tiny subset of true sends and would seed a misleading partial history.

## Repository Surface

### New file `src/deal_hunter/storage/repositories/sent_notification.py`

```python
class SentNotificationRepository:
    def __init__(self, session: Session) -> None: ...

    def record(
        self,
        *,
        alert_type: str,
        payload_json: str,
        deal_id: str | None = None,
        profile: str | None = None,
        sent_at: str | None = None,  # defaults to datetime.now().isoformat(); injectable for tests
    ) -> None: ...

    def last_sent_at(self, deal_id: str, alert_type: str) -> str | None: ...

    def list_recent(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        alert_type: str | None = None,
        profile: str | None = None,
        since: str | None = None,  # ISO string — sent_at >= since
    ) -> list[dict]: ...

    def count(
        self,
        *,
        alert_type: str | None = None,
        profile: str | None = None,
        since: str | None = None,
    ) -> int: ...
```

`list_recent` returns dicts shaped like the columns plus `payload` parsed back from JSON (so templates don't have to `json.loads` themselves). Ordered by `sent_at DESC`. `count` matches the filters of `list_recent` for paging.

### Exports

Append to `storage/repositories/__init__.py`:

```python
from deal_hunter.storage.repositories.sent_notification import SentNotificationRepository
...
__all__ = [..., "SentNotificationRepository", ...]
```

### Model

Add to `storage/models.py`:

```python
class SentNotification(Base):
    __tablename__ = "sent_notifications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    alert_type: Mapped[str] = mapped_column(String, nullable=False)
    deal_id: Mapped[str | None] = mapped_column(String, default=None)
    profile: Mapped[str | None] = mapped_column(String, default=None)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (
        Index("ix_sent_notifications_deal_id_alert_type", "deal_id", "alert_type", "sent_at"),
        Index("ix_sent_notifications_sent_at", "sent_at"),
    )
```

## Dashboard

### New route in `src/deal_hunter/api/routes/notifications.py`

Same router file as the settings page from PR #17 — keeps notification routes together.

```python
@router.get("/notifications/history", response_class=HTMLResponse)
def notifications_history_page(
    request: Request,
    page: int = 1,
    alert_type: str | None = None,
    profile: str | None = None,
    session: Session = Depends(get_db),
) -> HTMLResponse: ...
```

- 50 rows per page (matches `DEALS_PER_PAGE` for visual parity).
- `count(...)` for total, simple prev/next pagination.
- HX-Request → return the table partial; full page otherwise.

### New template `src/deal_hunter/api/templates/notifications_history.html`

Extends `base.html`. Sets `active_page = "notifications"` so the sidebar entry highlights from either Settings or History (per Section 5).

Top of content: sub-nav chips `Settings | History` with active-state styling — used on both `/notifications` and `/notifications/history`. The Settings template gets the same sub-nav added.

Filter row: `<select name="alert_type">` (Wszystkie / each alert_type value) and `<select name="profile">` (Wszystkie / each profile from the YAML directory). GET form, swaps via HTMX.

Table columns (`partials/notifications_history_table.html`):

| Time | Type | Profile | Subject |
|---|---|---|---|
| Humanized "5 min temu" + tooltip with absolute ISO | Colored chip (one colour per alert_type) | Profile name or "—" | For deal-bearing types: linked title + price; otherwise short payload preview |

Row click → HTMX-load an inline JSON view of the payload (no modal, no separate page).

### Sub-nav placement on `/notifications`

The Settings page template gets the same `Settings | History` sub-nav block at the top of the content area. No other changes to that page.

### No deletion / no editing

Read-only audit log. Retention is a future concern.

## Rollout Order

Single PR. Build order (each step a self-contained commit):

1. Migration `007_sent_notifications.py` + `SentNotification` model + index + model-columns test.
2. `SentNotificationRepository` + unit tests.
3. `notifiers/telegram/recorder.py` + tests (including the failure-swallowed-and-logged path).
4. Wire recording into each `send_*` method in `notifiers/telegram/transport.py`. Thread `profile` / `alert_type` kwargs from callers.
5. Wire `record_sent_notification` into `alerter.flush_queued` (queue-flush path) and `send_source_failure_alert`.
6. Cooldown rewire: filter takes `sent_repo`; `AlertService` accepts and threads it; `hunt_service` constructs it; tests updated.
7. Delete `AlertQueueRepository.last_price_drop_sent_at` and its tests.
8. Dashboard: `/notifications/history` route + template + partial + sub-nav on both notification pages + dashboard tests.

Backward compat: existing alerts continue to dispatch with the same behaviour on day 1. First-run cooldown reset is the only observable change in alerting behaviour.

## Testing

| Module | New / Extended | Coverage |
|---|---|---|
| `tests/test_migration_007_sent_notifications.py` | new | Adds table + two indexes; downgrade drops both; round-trip parallels migration 006's test shape. |
| `tests/test_models.py::test_sent_notifications_columns` | new | Pinned column-set assertion (mirrors `test_deals_columns`) so future schema drift is caught. |
| `tests/test_sent_notification_repository.py` | new | `record` writes a row with defaults; `last_sent_at` returns max-for-pair, ignores other types and deals, returns None when empty; `list_recent` filters + orders + paginates; `count` agrees with `len(list_recent(limit=big))`. |
| `tests/test_recorder.py` | new | Happy path inserts; injected session factory raising `SQLAlchemyError` → function returns `None`, no exception, `WARNING` log emitted. |
| `tests/test_services.py` | extend | Update `test_alert_service_filters_muted_deal_before_send` for new filter signature. Add `test_alert_service_records_after_successful_send`, `test_alert_service_does_not_record_on_telegram_failure`, `test_flush_queued_records_sent_notification`. |
| `tests/test_notification_filter.py` | extend | Rename `alert_repo` → `sent_repo` in helper + parameter names. All ten existing cases still pass. |
| `tests/test_quiet_hours.py` | reduce | Delete `TestAlertQueueDealId::test_last_price_drop_sent_at_*` (3 tests). Keep `test_queue_persists_deal_id`. |
| `tests/test_dashboard_notifications.py` | extend | New `TestNotificationsHistoryPage` with: empty-state render, single-row render with title visible, `alert_type` filter, `profile` filter, 60-row pagination split (page 1 = 50, page 2 = 10), sub-nav active-state on both pages. |

TDD per `superpowers:test-driven-development`. Pure-function and repository tests are test-first; UI wiring tests are test-first where the assertion is on a stable contract (status code, fragment presence, count), test-after where it'd just mirror the template.

## Open Items for Plan Stage

- **`payload` size sanity.** No row should approach SQLite's TEXT limit, but the `top_drops[:10]` digest payload could carry repeated deal blobs. Verify the slice is enough; if a digest snapshot is too verbose, store only deal IDs and re-resolve at display time.
- **Profile dropdown source.** The history filter offers a `profile` select; the values should match what's in `profiles/*.yaml` (use the existing `ProfileManager.list_profiles()` helper).
- **Sub-nav placement.** Section 5 says "top of content area"; confirm during implementation that the rendered position matches the existing dashboard's pattern (some pages use a header chip row, others a sub-tab strip). Match whichever already exists for consistency.
- **`payload` JSON-decode for templates.** The repository decodes once on the way out (`list_recent`). Verify the template doesn't accidentally `tojson`-encode it again — render via Jinja's `{{ x | tojson }}` only when explicitly showing the JSON view.
