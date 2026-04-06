# Web Dashboard — Design Spec

**Date:** 2026-04-06
**Roadmap item:** 3.3 Dashboard webowy
**Stitch project:** `projects/6965422606428222689` (4 screens)

## Context

Deal Hunter collects deals, tracks prices, and sends Telegram alerts. All data lives in SQLite (`state/deals.db`) and health state in `state/health.json`. There's no way to browse deals, inspect scoring, or check system health outside of CLI flags and Telegram messages. This dashboard provides a web UI for all of that.

## Architecture

```
Browser ──► FastAPI (port 8080) ──► SQLiteStorage + health.py
                │
                ├── Jinja2 templates (adapted from Stitch HTML)
                ├── HTMX for dynamic filtering/pagination
                ├── Chart.js via CDN for interactive charts
                └── Tailwind CSS via CDN (matching Stitch design tokens)
```

- **FastAPI** serves HTML via Jinja2 templates and JSON API endpoints for Chart.js data
- **HTMX** handles dynamic table filtering and pagination without a JS framework
- **Chart.js** (CDN) renders interactive price history and trend charts
- **Tailwind CSS** (CDN) with custom design tokens from the Stitch design system
- **No auth** — local access only (behind Tailscale or LAN)
- **Read-only** from SQLite (WAL mode handles concurrent reads safely alongside cron writes)
- Exception: deal status updates (watch/skip) write via `db.update_deal_status()`

## File Structure

```
dashboard.py                  FastAPI app: routes, API endpoints, template config
dashboard/
  templates/
    base.html                 Shared layout: sidebar nav, header, CDN imports
    deals.html                Deals Explorer — filters, deal table, metric cards
    deal_detail.html          Deal Detail — price chart, history table, actions
    health.html               System Health — source status, availability, events
    price_trends.html         Price History Analysis — drops table, categories
```

No `static/` directory needed — all assets via CDN (Tailwind, Chart.js, Material Symbols icons).

## Design System

From Stitch project design theme ("The Analytical Atelier"):

- **Fonts:** Manrope (headlines), Inter (body/data) — via Google Fonts CDN
- **Colors:** Blue-slate palette, primary `#005db5`, surface `#faf8ff`, no pure black
- **No-Line Rule:** No 1px borders for sections — use background color shifts for structure
- **Surfaces:** Layered containers (`surface` → `surface-container` → `surface-container-lowest`)
- **Roundness:** `0.75rem` for cards, full-round for status badges
- **Shadows:** Ambient only (40-60px blur, 4-8% opacity), no drop shadows on grid cards

## Screens

### 1. Deals Explorer (`/deals`)

**URL:** `GET /deals?profile=&source=&min_score=&category=&status=`

**Data source:** `db.get_deals(profile, source, min_score, category, status)`

**Components:**
- **Metric cards (top):**
  - Total deals count
  - Deals above alert threshold (percentage)
  - New deals today (deals with `first_seen` = today)
  - Active price drops count
- **Filter bar:** Profile, Source, Score Range, Category dropdowns + Clear Filters
  - HTMX: filters submit via `hx-get="/deals"` with `hx-target="#deals-table"` for partial refresh
- **Deals table:** ID, Title, Price, Source, Profile, Score, Status, Link
  - Clickable rows → `/deals/{deal_id}`
  - Status badges: active (teal), watching (blue), rejected (red)
  - Score displayed with color gradient (green high, red low)
- **Sidebar widgets:**
  - Category distribution (aggregated from deals)
  - Biggest recent price drop

### 2. Deal Detail (`/deals/{deal_id}`)

**URL:** `GET /deals/{deal_id}`

**Data sources:**
- `db.get_deal(deal_id)` — deal info
- `db.get_price_history(deal_id)` — for Chart.js
- `db.get_lowest_price(deal_id)` — highlight lowest
- `db.get_previous_price(deal_id)` — show delta

**Components:**
- **Header:** Deal title, current price, source badge, status badge
- **Price History Chart:** Chart.js line chart
  - Data from `/api/price-history/{deal_id}` (JSON endpoint)
  - Lowest price marked with red dot, highest with green
  - Time period selector (1M, 3M, All)
- **Action buttons:**
  - "Open Link" — external link to deal
  - "Watch" / "Skip" — calls `POST /api/deals/{deal_id}/status` → `db.update_deal_status()`
- **Price history table:** Date, Price columns from `price_history`
- **Deal metadata:** Source, Profile, Score, First seen, Last seen

### 3. System Health (`/health`)

**URL:** `GET /health`

**Data source:** `load_health()` from `health.py`

**Components:**
- **Operational Heartbeat:** Last run timestamp, overall status badge (ok/partial/error), duration
- **Summary cards:** Total deals across profiles, total alerts, version
- **Source Status Monitor table:**
  - Columns: Source, Status, Consecutive Failures, Last Success
  - Status badges: ok (teal), degraded (amber), down (red)
- **Profile Results table:**
  - Columns: Profile, Status, Deals Found, New Alerts, Errors
- **Recent events:** Errors from profile_results (if any)

### 4. Price History Analysis (`/price-trends`)

**URL:** `GET /price-trends?days=7`

**Data sources:**
- `db.get_price_drops(days=days)` — price drops
- `db.get_deals()` — for category aggregation

**Components:**
- **Summary cards:**
  - Total price drops in period
  - Average drop percentage
  - Biggest single drop
- **Price Drops table:**
  - Columns: Title, Source, Previous Price, Current Price, Drop %, Drop Amount
  - Time filter tabs: 7 Days / 24 Hours
  - Sorted by drop percentage descending
- **Category Distribution:** Pie/bar of deals by category
- **Category trend cards:** Top 3 categories with mini sparkline trend (Chart.js)

## API Endpoints (JSON)

| Endpoint | Method | Response | Used by |
|---|---|---|---|
| `/api/price-history/{deal_id}` | GET | `{labels: [...], prices: [...], lowest: N, highest: N}` | Chart.js on deal detail |
| `/api/deals` | GET | `[{id, title, price, source, ...}]` | HTMX table refresh |
| `/api/deals/{deal_id}/status` | POST | `{ok: true}` | Watch/Skip buttons |
| `/api/stats` | GET | `{total_deals, alerts_today, drops_count, ...}` | Metric cards refresh |

## Docker Compose

Add `deal-hunter-web` service:

```yaml
deal-hunter-web:
  build: .
  container_name: deal-hunter-web
  restart: unless-stopped
  env_file: .env
  environment:
    - TZ=${TZ:-Europe/Warsaw}
  entrypoint: ["tini", "--"]
  command: ["python", "-m", "uvicorn", "dashboard:app", "--host", "0.0.0.0", "--port", "8080"]
  ports:
    - "${DASHBOARD_PORT:-8080}:8080"
  volumes:
    - ./state:/app/state
  depends_on:
    - deal-hunter
```

## Dependencies

New packages to add:
- `fastapi` — web framework
- `uvicorn[standard]` — ASGI server
- `jinja2` — template engine

Add to both `requirements.txt` and `pyproject.toml` dependencies.

## Dockerfile Changes

Add to COPY section:
- `COPY dashboard.py .`
- `COPY dashboard/ dashboard/`

## Verification

1. `python -m uvicorn dashboard:app --port 8080` — starts without errors
2. `GET /deals` — renders deals table with data from SQLite
3. `GET /deals/{id}` — shows deal with Chart.js price chart
4. `GET /health` — shows source status from health.json
5. `GET /price-trends` — shows price drops table
6. Filter dropdowns on `/deals` update table via HTMX without full page reload
7. Watch/Skip buttons update deal status
8. `docker compose up -d` — all 3 services start (cron, bot, web)
