# Deals Explorer — Sorting, Date, Select-all, Mass Operations

**Status:** approved, implementing
**Date:** 2026-04-17

## Goal

Turn the deals explorer into a working bulk-editing surface. Today users have a
per-row Watch / Skip button and a 4-row Compare checkbox; the table has fixed
sort (score desc) and no visible date. This spec adds:

1. Clickable sort on every column except Trend and the selection checkbox.
2. A combined "added / last-seen" Date column (new column 8).
3. A header "select-all" checkbox backed by the current filter set (not just
   the visible page).
4. A bulk-action bar offering: Watch, Skip, Restore, Set Target, Compare,
   Export (CSV / JSON).
5. One unified row checkbox covering both Compare and bulk ops.

## Decisions

| Question | Answer |
|---|---|
| Which mass operations? | Watch / Skip / Restore, Set Target Price, Compare, Export (CSV + JSON). |
| Select-all scope? | Always-all-filtered. Header checkbox represents the entire filter set, even across pages. |
| Date column source? | Both `first_seen_at` (primary: "added Xd ago") and `last_seen_at` (secondary: "seen Ym ago"). Sort targets `first_seen_at`. |
| Which columns sort? | Every column except Trend and the selection checkbox. |
| Selection model? | Single row checkbox. Compare is one of the bulk actions; disabled (with tooltip) when selection ≠ 2–4. |
| Payload shape? | Approach B — bulk endpoint accepts either `{ids:[...]}` or `{filter:{...}, excluded:[...]}`. Filter mode scales to 50 000-row ops without a huge wire payload. |

## Architecture

### Selection state (client)

A single JS module `static/js/selection.js` owns:

```js
{ mode: "ids" | "filter",
  ids: Set<string>,          // when mode === "ids"
  filter: {...queryParams},  // when mode === "filter"
  excluded: Set<string> }    // when mode === "filter"
```

- Row checkbox click → `mode="ids"`, toggle id in `ids`.
- Header checkbox click → `mode="filter"`, snapshot current URL params, clear `excluded`.
- Row uncheck in filter mode → add id to `excluded`.
- Any filter OR sort change → `selection.clear()`. Pagination does NOT clear.

### Wire payload

```
POST /api/deals/bulk  (JSON)
{
  action: "set-status" | "set-target" | "compare",
  ids?: [...]                                        # approach A path
  filter?: {profile, source, min_score, category, status},
  excluded?: [...],                                  # approach B path
  status?: "watching" | "rejected" | "active",       # for set-status
  target_price?: int,                                # for set-target
}
```

Single endpoint dispatches on `action`. Compare returns
`{"redirect": "/compare?ids=..."}` capped at 4 ids server-side.

### Sort

URL-owned state: `?sort=<col>&dir=asc|desc`. Default `score desc` (today's
behaviour). Column allowlist in `OfferRepository.SORT_COLUMNS` — unknown sort
silently falls back to default; route-level Pydantic `Literal` rejects at the
edge. Tiebreaker: `ORDER BY <col>, id` for stable pagination.

### Date column

New column between Score and Status. Two lines:

```
added 3d ago        ← first_seen_at, text-sm
seen 5m ago         ← last_seen_at, text-xs text-on-surface-variant
```

Secondary line hidden when `last_seen_at` is within a minute of
`first_seen_at`. Rendered by a new `humanize_age(iso, now)` Jinja filter.
`NULLS LAST` when sorting.

## New / modified files

### Backend

- `src/deal_hunter/storage/repositories/offer.py`
  - `SORT_COLUMNS` dict (allowlist).
  - `get_filtered` — add `sort`, `direction` params + `id` tiebreaker.
  - `get_filtered_ids(...)` — ids-only query for "Select all" fetch.
  - `bulk_update_status(ids, status) -> int`.
  - `iter_filtered(chunk=1000, **filters) -> Iterator[dict]` for export streaming.
- `src/deal_hunter/storage/repositories/watchlist.py`
  - `bulk_upsert(ids, target_price) -> int` — SQLite `INSERT ... ON CONFLICT`.
- `src/deal_hunter/storage/repositories/feedback.py`
  - `record_many(ids, action) -> int` — executemany.
- `src/deal_hunter/api/view_services/deal_service.py`
  - Thread `sort`, `direction` through `get_deals_page`; include in `filter_params`.
- `src/deal_hunter/api/routes/deals.py`
  - `deals_page` — accept `sort`, `dir` query params.
  - `GET /api/deals/count?<filters>` → `{"count": int}`.
  - `GET /api/deals/ids?<filters>` → `{"ids": [...]}`.
  - `POST /api/deals/bulk` — unified bulk endpoint.
  - `GET /api/deals/export?format=csv|json&<filters>` — streaming response.
- `src/deal_hunter/api/schemas.py`
  - `BulkRequest`, `FilterParams` Pydantic models.
- `src/deal_hunter/api/__init__.py` (or filters file)
  - `humanize_age` Jinja filter.

### Templates

- `templates/partials/deals_table.html`
  - Sort-header macro `sort_th(label, col)`.
  - New Date column (col 8).
  - Rename row checkbox class `compare-cb` → `deal-cb`; header gets `#select-all-cb`.
  - `data-total-filtered="..."` on table wrapper.
- `templates/deals.html`
  - Mount points: `#bulk-action-bar`, `#bulk-toast`, `#confirm-dialog-mount`.
  - Include new JS modules.
- `templates/partials/bulk_action_bar.html` (new) — the sticky strip; rendered
  empty on page load, populated by JS when selection is non-empty.
- `templates/partials/confirm_dialog.html` (new) — reusable confirmation modal.
- `templates/partials/bulk_toast.html` (new) — toast snippet returned by
  the bulk endpoint on success.

### Frontend JS

- `static/js/selection.js` — state module with public API described above.
- `static/js/bulk_actions.js` — wires buttons, dispatches fetch + JSON to
  `/api/deals/bulk`, handles toast + table reload.
- `static/js/confirm.js` — `await confirm({title, body})` helper.
- `static/js/compare.js` — DELETE. Compare is now one of the bulk actions,
  driven by `selection.js`.

### Tests

- `tests/test_repositories.py` — sort variants, `get_filtered_ids`,
  `bulk_update_status`, `iter_filtered` chunking, bulk_upsert, record_many,
  NULL-last for date sort.
- `tests/test_dashboard.py` — new `TestBulkEndpoint` class covering each
  action + both payload shapes, 413 cap, export CSV/JSON headers.
- `tests/e2e/test_bulk_ops.py` (new) — header-checkbox → bulk Watch, exclude
  path, filter change clears selection, sort cycles, date column content,
  confirm dialog, Compare button states, CSV export download, pagination
  preserves selection, bad sort URL = 422.

## Constraints & guardrails

- Server hard cap **100 000 rows** per bulk operation → 413 if exceeded.
- Destructive client confirmation for Skip (mass + per-row) and for Restore
  when count > 50. Set-Target always confirms (high-intent op).
- Export streams with `yield_per(1000)` — no in-memory materialisation.
- Unknown `sort=` silently falls back to `score desc` in the repo; route rejects
  with 422 via Pydantic `Literal`.
- Selection clears on any filter OR sort change; survives pagination.
- Concurrent updates: no locking — table re-fetches after any bulk op; last
  write wins for status/target fields.

## Out of scope

- Keyboard shortcuts for bulk actions.
- Accessibility audit of the new action bar (follow-up).
- 100 k-row export performance SLO.
- Server-persisted selection (cross-tab, cross-session).
