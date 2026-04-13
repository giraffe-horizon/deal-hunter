# Products & Offers — migrating from "deal feed" to "products with pinned offers"

**Date:** 2026-04-13
**Updated:** 2026-04-13 — re-aligned to current repo (post Phase 3-6 refactor: SQLAlchemy ORM, Alembic migrations, service layer, Pydantic dashboard schemas). Later same-day update: Phase A decomposed into **A1** (table + class rename only, column names preserved) and **A2** (column renames + new schema + event writes) to keep each migration's blast radius tight.
**Status:** design (approved by user through Q&A dialog). Phase A1 in progress on worktree `phase-a1-rename` (commits `2e1cf04`, `bf9df9c`, `cdd7aba`: Alembic 003 + ORM class rename).
**Goal:** evolutionary transformation of deal-hunter from a per-Deal feed dashboard into a per-Product dashboard with cross-source price history and pinned offers.

## Context

Deal-hunter currently collects deals mainly from Pepper, Ceneo, and a few YAML-based stores (proshop, x-kom, morele) plus Allegro RSS. Each deal is a `Deal` record with unique `id = "{source}:{native_id}"`. The dashboard shows a feed of these deals.

Target model:
- the same product from different sources is grouped,
- a product has its own cross-source price history,
- a product has multiple active offers with links,
- existing "deals" become **events** (new_listing, price_drop, back_in_stock) pinned to products.

**Primary design risk:** entity resolution. A false merge (combining two different products into one) is worse than a missing merge (leaving them separate). Matching must be conservative and layered.

## Principles

- Evolution, not rewrite. Strangler pattern with feature flag `PRODUCT_MODEL_ENABLED`.
- False merge > missing merge: high auto-merge thresholds (0.90+ for L2), `required_match_attrs` per category as a hard blocker.
- Keep **raw/source-specific title** (in Offer/Deal, never overwritten) separate from **normalized title** (in Product, produced by the normalizer).
- Variant = separate Product. Family deferred (only `attributes.family_key` string).
- Matching limited to a single `category` (hard cross-profile barrier).

---

## 1. Domain architecture

### Refactor note (naming)

The existing `Deal` SQLAlchemy model (in `storage/models.py`) is, in practice, an **Offer**: one row per active offer from one source, upserted on each fetch, carrying `first_seen`, `last_seen`, `price`, `link`, `status`. It is not an event log.

We therefore rename at the code level:
- Python class `Deal` → `Offer`
- Table `deals` → `offers` (Alembic migration, no data loss — PK values preserved)
- Field `Deal.id` becomes `Offer.id`, format `"{source}:{native_id}"` **preserved verbatim** (feedback_bot callback_data, CLI `--price-chart`, systemd units keep working — they reference the id value, not the class name).
- `DealRepository` → `OfferRepository`.
- A separate new table `deal_events` (Python class `DealEvent`) holds the append-only event log (`new_listing`, `price_drop`, `price_increase`, `back_in_stock`, `expiring`).

### Entities

- **Product** — canonical representation of a specific variant/SKU (one bike size, one HDD capacity). Carries normalized title, brand, model, structural attributes, review status, last match confidence, audit metadata. Primary key: UUID. No slugs — dashboard URL is `/products/{uuid}`.
- **ProductAlias** — any known external identifier mapping to a Product (EAN, ASIN, MPN, store SKU, canonical URL, `ceneo_group_id`, `manual_merge_key`). Primary carrier of certainty — matcher prefers attaching an alias over dragging title similarity.
- **Offer** (renamed from `Deal`) — active offer from a single source, identity-stable over time. One URL/`source_native_id` lives for its whole lifecycle; `current_price` and `availability` change. Holds `raw_title`, extracted `attributes_hint`, time metadata.
- **OfferPayloadHistory** — separate table with the last N=10 raw_payload snapshots per Offer (FIFO). Used for debugging and forensics on false merges.
- **DealEvent** — append-only event log. One row per notable transition: `new_listing`, `price_drop`, `price_increase`, `back_in_stock`, `expiring`. Carries `offer_id`, denormalized `product_id`, `price_at_event`, `payload` (diff/context for the alert). This is what the dashboard product-detail timeline renders.
- **PricePoint** (existing `PriceHistory` model, extended) — price point per Offer with cross-source aggregation via `product_id`. Stores `price_pln`, `price_original`, `currency_original`, `fx_rate_used`, `recorded_at`, `availability`.
- **MatchReview** — manual review queue entry: offer without confident match + top-N candidates with confidence + reason + priority.
- **MatchDecision** — audit log of every matcher decision (auto L1/L2/L3, manual approve/reject/split/merge) with the signals that drove it.
- **FxRate** — NBP rate cache.

### Relationships

- Product 1:N ProductAlias, 1:N Offer, 1:N PricePoint, 1:N DealEvent
- Offer 1:N DealEvent, 1:N PricePoint, 1:N OfferPayloadHistory
- MatchReview N:1 Offer, M:N (suggested) Product

### Relationship to existing in-memory dedup

`services/fetcher.py::DealFetcher.deduplicate()` (0.85 fuzzy title + ±5% price) is a **per-fetch in-memory** collapse step: if Pepper and Ceneo return the same offer in a single run, only one survives. That stays. Product matching is a **persistent, cross-session** layer: each surviving offer gets linked to (or creates) a Product. The two are complementary. The existing `dedup:` profile config keeps working.

### Price history

- Source of truth: PricePoint per Offer.
- `product_id` denormalized in PricePoint → single query to assemble a cross-source product timeline.
- "Lowest price ever" = MIN(price_pln) WHERE product_id = X.
- Price is **not** a match signal (differs by definition).
- With different original currencies: alert threshold (`min_drop_percent`, `min_drop_amount`) computed on `price_original` when currency has not changed — avoids false alerts driven by FX movement.

---

## 2. Data model (SQLAlchemy ORM on SQLite)

All new models live in `storage/models.py` alongside existing ones. All schema changes land via Alembic migrations in `storage/migrations/versions/` (existing: `001_baseline`, `002_seen_deals`). All data access goes through repositories in `storage/repositories.py`.

### products

| column | type | notes |
|---|---|---|
| id | TEXT PK | UUID v4 |
| canonical_title | TEXT NOT NULL | normalized |
| brand | TEXT | nullable, indexed |
| model | TEXT | nullable, indexed |
| category | TEXT NOT NULL | aligned with profile (bikes, nas_hdd, ...) |
| attributes | JSON NOT NULL | {size, frame_color, year, capacity_tb, form_factor, family_key, ...} |
| canonical_image_url | TEXT | |
| review_status | TEXT NOT NULL | enum: `auto` \| `confirmed` \| `needs_review` \| `rejected` |
| confidence_score | REAL | last match score that produced this row |
| merged_from | JSON | list of product ids merged into this one (audit) |
| archived | INTEGER NOT NULL DEFAULT 0 | soft-delete |
| created_at | TEXT NOT NULL | ISO |
| updated_at | TEXT NOT NULL | ISO |

Indexes: `(brand, model)`, `(category)`, FTS5 on `canonical_title`, `(archived, updated_at)`.

### product_aliases

| column | type | notes |
|---|---|---|
| id | INTEGER PK | |
| product_id | TEXT FK NOT NULL | ON DELETE CASCADE |
| identifier_type | TEXT NOT NULL | enum: `ean` \| `asin` \| `mpn` \| `sku` \| `canonical_url` \| `source_native_id` \| `ceneo_group_id` \| `manual_merge_key` |
| identifier_value | TEXT NOT NULL | |
| source | TEXT | NULL for global (ean/asin/mpn) |
| confidence | REAL NOT NULL | |
| created_by | TEXT NOT NULL | `auto` \| `manual` |
| created_at | TEXT NOT NULL | |

Uniqueness: `UNIQUE (identifier_type, identifier_value, COALESCE(source, ''))`. Index on `product_id`.

### offers (renamed from `deals`)

The existing `deals` table is renamed to `offers` via **two** Alembic migrations:

- **`003_rename_deals_to_offers`** (Phase A1) — table rename only. Column names are preserved verbatim (`title`, `price`, `link`, `first_seen`, `last_seen`). Index `idx_deals_profile_score` → `idx_offers_profile_score`. Sibling table `price_history` → `price_points` with column names (`deal_id`, `price`, `recorded_at`) also preserved. This keeps `_to_dict()` keys, templates, Telegram payloads, and dashboard APIs untouched, so A1 ships as a pure structural rename with no caller-visible contract change.
- **`004_products_schema`** (Phase A2) — column renames + additive new columns + new sibling tables. This is where the product model actually starts to exist.

The PK `id TEXT` keeps the format `"{source}:{native_id}"` throughout both revisions — no value migration at any step.

**Existing columns renamed in A2** (to align with product-model vocabulary):
- `title` → `raw_title` (never overwritten after first write)
- `price` → `current_price_pln`
- `link` → `url`
- `first_seen` → `first_seen_at`
- `last_seen` → `last_seen_at`

**Existing columns kept as-is:** `id, source, description, image_url, profile, score, category, status`.

**New columns added:**
- `product_id` TEXT FK → `products.id`, NULL allowed (pre-match)
- `source_native_id` TEXT — extracted from existing `id` (split on first `:`), backfilled during migration; used by matcher for cross-source lookups
- `current_price_original` INTEGER — smallest unit in original currency
- `currency_original` TEXT NOT NULL DEFAULT `'PLN'`
- `fx_rate_used` REAL — NULL for PLN
- `availability` TEXT — `in_stock` \| `out_of_stock` \| `unknown`
- `attributes_hint` JSON — extracted pre-match
- `is_active` INTEGER NOT NULL DEFAULT 1

Variant suffix (e.g. `"proshop:12345#size=54"`): the full value lives in PK `id`; `source_native_id` holds the portion after the first colon (`12345#size=54`).

Uniqueness: PK on `id`; `UNIQUE (source, source_native_id)`; `UNIQUE (source, url)`. Indexes: `product_id`, `last_seen_at`, `(source, is_active)`, existing `idx_deals_profile_score` renamed to `idx_offers_profile_score`.

Python: `class Deal` → `class Offer` (renamed in `storage/models.py`); `DealRepository` → `OfferRepository` (renamed in `storage/repositories.py`, all callers updated). Existing `Deal` dataclass in `sources/base.py` (the in-flight ingest DTO) stays named `Deal` to avoid rippling into every `Source` subclass — it represents the *raw fetch result*, distinct from the persisted `Offer` ORM model.

### offer_payload_history

| column | type | notes |
|---|---|---|
| id | INTEGER PK | |
| offer_id | TEXT FK NOT NULL | → `offers.id`, ON DELETE CASCADE |
| raw_payload | JSON NOT NULL | scrape snapshot |
| captured_at | TEXT NOT NULL | ISO |

Retention: max 10 rows per `offer_id`, FIFO. Cleanup inline on every `touch_offer` or via cron.

### deal_events (new)

Append-only event log. One row per notable transition on an offer. Renders as the per-product timeline in the dashboard.

| column | type | notes |
|---|---|---|
| id | INTEGER PK | |
| offer_id | TEXT FK NOT NULL | → `offers.id` |
| product_id | TEXT FK | denormalized for fast per-product queries, NULL if unmatched |
| event_type | TEXT NOT NULL | enum: `new_listing` \| `price_drop` \| `price_increase` \| `back_in_stock` \| `expiring` |
| price_at_event | INTEGER | in PLN, smallest unit |
| payload | JSON | event-specific context (e.g. `{old_price, new_price, diff_pct}` for drops) |
| created_at | TEXT NOT NULL | ISO |
| notified | INTEGER NOT NULL DEFAULT 0 | 0/1 — has the notifier sent this? |

Indexes: `(offer_id, created_at DESC)`, `(product_id, created_at DESC)`, `(event_type, created_at DESC)`, `(notified)`.

### price_history (renamed to price_points, extension of existing)

Rename the table `price_history` → `price_points` (matches the domain noun "PricePoint" used throughout spec). Python model `PriceHistory` → `PricePoint`.

Existing columns kept: `deal_id` (renamed to `offer_id` and retyped as FK to `offers.id`), `price` (renamed to `price_pln`), `recorded_at`.

New columns added:
- `product_id` TEXT FK — denormalized
- `price_original` INTEGER
- `currency_original` TEXT DEFAULT `'PLN'`
- `fx_rate_used` REAL
- `availability` TEXT

Indexes: `(offer_id, recorded_at DESC)`, `(product_id, recorded_at DESC)`.

### match_reviews

| column | type | notes |
|---|---|---|
| id | INTEGER PK | |
| offer_id | TEXT FK NOT NULL | → `offers.id` |
| candidate_product_id | TEXT FK | NULL when no candidate |
| suggested_products | JSON | top-N candidates with confidence |
| best_confidence | REAL | |
| reason | TEXT | e.g. `"fuzzy_only:brand_unknown"`, `"L2_borderline:size_null_on_candidate"` |
| status | TEXT NOT NULL | `pending` \| `approved` \| `rejected` \| `auto_resolved` \| `superseded` \| `audit_sample` |
| priority | INTEGER NOT NULL | computed: `score + (temp/20 if Pepper) + (5 if within budget)` |
| decided_by | TEXT | |
| decided_at | TEXT | |
| created_at | TEXT NOT NULL | |

Indexes: `(status, priority DESC)`, `offer_id`.

### match_decisions (audit log)

| column | type | notes |
|---|---|---|
| id | INTEGER PK | |
| offer_id | TEXT FK | → `offers.id` |
| product_id | TEXT FK | |
| decision_type | TEXT NOT NULL | `auto_hard_id` \| `auto_strong` \| `auto_fuzzy` \| `manual_approve` \| `manual_reject` \| `manual_split` \| `manual_merge` |
| confidence | REAL | |
| signals | JSON | signals that drove the decision (what matched, what rejected) |
| actor | TEXT NOT NULL | `auto` \| user name (for now `"local"`) |
| created_at | TEXT NOT NULL | |
| undo_snapshot | JSON | pre-change snapshot for 7-day undo window |

Indexes: `(offer_id)`, `(product_id)`, `(created_at)`.

### fx_rates

| column | type | notes |
|---|---|---|
| currency | TEXT PK | currency code (EUR, USD, ...) |
| rate_to_pln | REAL NOT NULL | rate |
| fetched_at | TEXT NOT NULL | ISO |
| table_no | TEXT | NBP table number (audit) |

Refresh: cron `scripts/fetch_fx_rates.py` once daily. Fallback on downtime: reuse last row and emit warning log when `fetched_at` > 48h.

### Required fields (input validation)

- Product: `id, canonical_title, category, attributes, review_status, created_at, updated_at`.
- Offer: `id, source, source_native_id, url, raw_title, currency_original, first_seen_at, last_seen_at, is_active`.
- ProductAlias: `product_id, identifier_type, identifier_value, confidence, created_by, created_at`.
- DealEvent: `offer_id, event_type, created_at`.
- MatchDecision: `decision_type, actor, created_at` (plus one of `offer_id`/`product_id`).

---

## 3. Matching strategy

### Pipeline

Runs from strongest to weakest signal; stops at the first decision.

**L1 — Hard identifiers (confidence = 1.0, auto-match, no review)**
- Offer has EAN/ASIN/MPN and a matching ProductAlias → match.
- Offer canonical URL matches `canonical_url` in ProductAlias (per source) → match.
- `(source, source_native_id)` already known → idempotent match (subsequent refresh).
- No manual `manual_reject` in match_decisions for this pair (negative evidence).

**L2 — Strong match (confidence 0.85–0.98)**
- Requires non-empty `brand` and `model` in `attributes_hint`.
- Requires 100% agreement on `required_match_attrs` for the category (see below).
- Blocking key: `(brand, model, category)` — narrows candidates.
- Metric: `token_set_ratio` of normalized title (rapidfuzz) ≥ 0.90.
- **`ceneo_group_id` as an L2 signal** (not L1) — if Ceneo groups offer X with group Y, treat as a strong signal but still require `required_match_attrs` agreement. Base confidence 0.92.
- Auto threshold: ≥ 0.90 and zero contradictions → auto-match.
- 0.85–0.90 → review queue.
- Contradiction on `required_match_attrs` (both sides populated and different) → **no match, no review** — create a new Product.
- Null on one side of `required_match_attrs` → **no match, no review** (we do not relax obligatory attributes).

**L3 — Weak match (confidence 0.60–0.84)**
- FTS5 + rapidfuzz across the corpus, no confident brand/model.
- Always routes to review queue, never auto-merges.
- Top-3 candidates stored in `suggested_products`.

**L4 — No match (confidence < 0.60)**
- Create a new Product from `attributes_hint`, `review_status = auto`.
- Post-MVP: background sweep periodically re-matches these.

### required_match_attrs per category

Declared in profile YAML as `required_match_attrs:`:

- **bikes**: `size`, `frame_color`, `year`
- **nas_hdd**: `capacity_tb`, `form_factor`

For other profiles (not decided at this time) — defined per profile during implementation. `utils/validation.py` must require an explicit list (empty allowed — but conscious).

### Merge vs no-merge rules

- A contradiction on `required_match_attrs` **always blocks** a merge (even at token_set_ratio 1.0).
- Auto-merge requires confidence ≥ 0.90; auto-split does not exist (manual only).
- Negative evidence ("sticky no"): a pair `(offer_id, product_id)` with manual `reject` is never proposed again.
- Price and source are not match signals.
- Cross-category matching is blocked (hard barrier).

### Variants

- Variant = separate Product. Conservative by default.
- N Offers per variant when a store page exposes a single URL with a size selector. Suffix in `source_native_id`: `proshop:12345#size=54`, `proshop:12345#size=56`.
- Family grouping: `attributes.family_key` (string computed from brand+model+year). `ProductFamily` entity is out of MVP scope.

### Defenses against false merge

- High auto thresholds (L2 ≥ 0.90 + 100% required attrs agreement).
- Canary audit: each week sample 20 auto-L2 matches into `match_reviews` with status `audit_sample` for manual review. Metric: `precision@L2`.
- Weekly alert when `false_merge_rate > 0.5%` → cutover gate.
- Undo per decision within a 7-day window — `match_decisions.undo_snapshot` restores products + aliases state.

### Manual review queue

- `/review` view sorted by `priority DESC`.
- Priority = `deal_score + (temperature/20 if Pepper) + (5 if within budget)`.
- Per row: offer (raw_title, image, price, source) + top-3 candidates with confidence + actions: `approve_as`, `reject_create_new`, `merge_products`, `skip`.
- Every decision → `match_decisions` + optional new `product_aliases` of type `manual_merge_key` (next time L1 matches).

### Currency conversion (new in MVP)

- NBP rate fetched once daily (endpoint `https://api.nbp.pl/api/exchangerates/tables/A/`).
- Cached in SQLite `fx_rates` table (see schema). Fallback: last known rate when NBP is down, with a warning log.
- PricePoint stores `price_original` + `currency_original` + `price_pln` + `fx_rate_used`.
- Price-drop alert computed on `price_original` when currency has not changed (prevents FX-driven false alerts). If currency changed (rare) — compute on `price_pln` with an audit note.

---

## 4. Migration plan

Strangler pattern, feature flag `PRODUCT_MODEL_ENABLED`, dual-write, single-read-old → dual-read → cutover. All schema changes are Alembic revisions in `storage/migrations/versions/`.

**Phase 0 — schema only (two Alembic revisions, split over A1 and A2)**
- `003_rename_deals_to_offers.py` (Phase A1) — rename table `deals` → `offers` and `price_history` → `price_points`; rename index `idx_deals_profile_score` → `idx_offers_profile_score`; retarget FKs on `feedback`, `watchlist`, and the price-point child table onto `offers(id)`. **Column names preserved**: `title`, `price`, `link`, `first_seen`, `last_seen` on offers; `deal_id`, `price`, `recorded_at` on price_points. Python: `class Deal` → `class Offer`, `class PriceHistory` → `class PricePoint`, `DealRepository` → `OfferRepository` (with short-lived backward-compat alias during the callers-migration pass). Downgrade reverses rename.
- `004_products_schema.py` (Phase A2) — rename columns (`title`→`raw_title`, `price`→`current_price_pln`, `link`→`url`, `first_seen`→`first_seen_at`, `last_seen`→`last_seen_at` on offers; `deal_id`→`offer_id`, `price`→`price_pln` on price_points); add new columns on `offers` (`product_id`, `source_native_id`, `current_price_original`, `currency_original`, `fx_rate_used`, `availability`, `attributes_hint`, `is_active`); add new columns on `price_points` (`product_id`, `price_original`, `currency_original`, `fx_rate_used`, `availability`); create new tables `products`, `product_aliases`, `offer_payload_history`, `deal_events`, `match_reviews`, `match_decisions`, `fx_rates`; backfill `source_native_id` from existing `offers.id` (split on first `:`).
- After `003` alone: full test suite green, zero caller-visible contract change. After `004`: `_to_dict()` keys change (external contract break) — handle in same PR as the dashboard/Telegram/bot adapters.

**Phase 1 — dual-write events + FX-aware prices**
- Ingest writes to `offers` (as today, via renamed `OfferRepository`), appends to `offer_payload_history` (new), emits `deal_events` rows for detected transitions (new_listing, price_drop derived from the existing `services/price_tracker.py`).
- PricePoint writes include `price_original`, `currency_original`, `price_pln`, `fx_rate_used` (initially currency_original always 'PLN' until Phase B lands NBP).
- `product_id` on offers stays NULL.

**Phase 2 — backfill Products**
- `cli/backfill_products.py` (new CLI entrypoint) iterates Offers with `product_id IS NULL`, runs L1+L2 pipeline, creates Product where no match exists.
- Logs to `match_decisions`. Resumable (checkpointed per batch in a `backfill_state` JSON or a dedicated column).
- After backfill: `offers.product_id` populated ≥ 95%.

**Phase 3 — dual-read dashboard**
- `/products` endpoints live under a feature flag: environment variable `PRODUCT_MODEL_ENABLED=true` enables the "Products" tab in sidebar nav and exposes routes. Default off.
- `/deals` (listing) keeps serving the classic view from the renamed `offers` table (same data, same UI).
- Users compare.

**Phase 4 — cutover**
- `PRODUCT_MODEL_ENABLED=true` becomes the default.
- `/deals` view stays as the per-source event feed (reads from `deal_events` joined with `offers`); `/products` becomes the primary discovery view.
- Telegram alerts add a "Produkt" deep-link button.

**Phase 5 — cleanup (optional, ~1 month later)**
- Remove the feature flag, remove any legacy compat shims.

### Backward compatibility (hard guarantees)

- `Offer.id = "{source}:{native_id}"` format preserved **verbatim** (value is not migrated, only the table it lives in is renamed) — feedback_bot callback_data, CLI `--price-chart "pepper:12345"`, systemd timers all keep working.
- `watchlist.deal_id` FK: during migration `003_rename_deals_to_offers`, the FK target retargets from `deals(id)` to `offers(id)` — the id values are identical. Column name stays `deal_id` for stability; future migration may rename to `offer_id` in a cleanup pass.
- Old offers without `product_id` after backfill: visible as "legacy, unmatched" on the `/review` queue with low priority; not hidden from `/deals` listing.

### Historical data migration

- Offers: no reconstruction needed — the existing `deals` table rows become `offers` rows 1:1.
- Price points: existing `price_history` rows become `price_points` rows 1:1 (`deal_id` → `offer_id` column rename).
- `deal_events`: we do NOT backfill historical events. The table starts empty; only events produced after the cutover are recorded. Historical price drops remain available via `price_points`, just not as event rows.

### Dual-write vs adapter

Dual-write, because writes are infrequent (crons every 30min) and read consistency on both models is critical for cutover confidence.

---

## 5. Implementation phases

### Phase A1 — Table + class rename (column names preserved)

- **Goal:** Ship Alembic `003_rename_deals_to_offers` as a pure structural rename. No contract changes visible to dashboard, Telegram, or CLI.
- **Scope:**
  - `storage/migrations/versions/003_rename_deals_to_offers.py` — `rename_table` only; preserve every column name.
  - `storage/models.py` — `class Deal` → `class Offer`, `class PriceHistory` → `class PricePoint`; ForeignKey targets retargeted to `offers(id)` on `Feedback`, `WatchlistItem`, `PricePoint`; relationship attribute `deal` → `offer` (back_populates aligned). `SeenDeal` and `AlertQueue` untouched.
  - `storage/repositories.py` — `DealRepository` → `OfferRepository`; raw SQL updated (`FROM deals` → `FROM offers`, `INSERT INTO price_history` → `INSERT INTO price_points`, `JOIN deals d` → `JOIN offers d`). Short-lived `DealRepository = OfferRepository` alias during caller migration; removed at end of A1.
  - All callers: `tests/conftest.py`, `services/*`, `dashboard/routes/*`, `dashboard/services/*`, `visualization/charts.py`, `deal_hunter.py`, `feedback_bot.py`, `scripts/migrate_json_state.py`.
  - `tests/test_migration_003_rename.py` — round-trip test: upgrade, insert, downgrade, re-upgrade, verify data survives.
- **Dependencies:** none.
- **Risks:** rename touches many files; easy to miss a raw-SQL string. Mitigated by the `FROM (deals|price_history)` grep gate in the plan's Definition of Done.
- **DoD:** Alembic `003` round-trips cleanly; `grep -rn --include='*.py' -E '(FROM|JOIN|INTO|UPDATE)\s+(deals|price_history)\b'` returns only the migration round-trip test; `grep -rn '\bDealRepository\b'` returns zero outside docs; full test suite matches pre-A1 baseline; `deal_hunter.py --list` and `--health` import cleanly.
- **Plan:** [docs/superpowers/plans/2026-04-13-phase-a1-rename-deals-to-offers.md](docs/superpowers/plans/2026-04-13-phase-a1-rename-deals-to-offers.md). In progress — Tasks 0–2 shipped on worktree `phase-a1-rename`.

### Phase A2 — Column renames + new schema + event writes

- **Goal:** Alembic `004_products_schema` lands; every ingest appends to `offer_payload_history` and `deal_events`. `_to_dict()` external keys change; dashboard, Telegram, and bot payload assembly all migrate in lockstep.
- **Scope:**
  - `storage/migrations/versions/004_products_schema.py` — column renames on `offers` and `price_points` + additive new columns + new tables (`products`, `product_aliases`, `offer_payload_history`, `deal_events`, `match_reviews`, `match_decisions`, `fx_rates`) + `source_native_id` backfill.
  - `storage/models.py` — new models `Product`, `ProductAlias`, `OfferPayloadHistory`, `DealEvent`, `MatchReview`, `MatchDecision`, `FxRate`; existing models gain the new columns.
  - `storage/repositories.py` — new `ProductRepository`, `ProductAliasRepository`, `OfferPayloadHistoryRepository`, `DealEventRepository`, `MatchReviewRepository`, `MatchDecisionRepository`, `FxRateRepository`; `OfferRepository._to_dict()` emits new keys (`raw_title`, `current_price_pln`, `url`, `first_seen_at`, `last_seen_at`).
  - Dashboard templates, JSON API, Telegram alert builders, feedback-bot handlers: accept the new dict keys (with a transitional key-alias adapter if the commit is otherwise too large).
  - `services/fetcher.py` and `services/alerter.py` — on upsert append payload history (N=10 FIFO), emit event rows (`new_listing`, `price_drop`, `price_increase`, `back_in_stock`, `expiring`).
  - Test sweep to the new names.
- **Dependencies:** A1 complete.
- **Risks:** Contract change is visible end-to-end. Concurrent-cron integrity on event writes. SQLite `ALTER COLUMN` requires the CREATE-new → INSERT-SELECT → DROP-old → RENAME pattern.
- **DoD:** `alembic upgrade head` + `alembic downgrade -1` round-trips on a DB copy; full test suite green; `OfferPayloadHistory` capped at 10 per offer; `DealEvent` rows emitted for ingest transitions; `/deals` and Telegram alerts visually identical to pre-A2.
- **Plan:** to be written at `docs/superpowers/plans/2026-04-13-phase-a2-products-schema.md`.

### Phase B — Attribute + identifier extractor + NBP FX

- **Goal:** for every Offer we extract `brand, model, attributes_hint` and where available `ean, sku, canonical_url, mpn, ceneo_group_id`. NBP fetcher works.
- **Scope:**
  - New subpackage `services/matching/` with `extractor.py`, `normalizer.py`.
  - New module `services/fx/nbp.py` (NBP client with SQLite-cached `fx_rates`, fallback on downtime).
  - New CLI: `cli/fetch_fx_rates.py` (daily cron entrypoint).
  - `stores/*.yaml` — new sections `identifiers:` (ean, sku, mpn, canonical_url_pattern, ceneo_group_id selectors) and `attributes:` (per-category selectors).
  - `utils/validation.py` — validation for new YAML sections.
  - `profiles/*.yaml` — new `required_match_attrs:` list; validator requires it (empty allowed, but must be explicit).
  - Ingest writes `current_price_original`, `currency_original`, `fx_rate_used`, `price_pln` to PricePoint.
- **Dependencies:** A.
- **Risks:** low EAN/SKU coverage → L2 must carry the weight; NBP API downtime → fallback to last rate.
- **DoD:** per-source tests on HTML/JSON fixtures; identifier coverage report per source in logs; `brand+model` coverage ≥ 80% on tagged test set; NBP rate cached in DB, fallback tested.

### Phase C — Matching pipeline + Product creation + backfill

- **Goal:** L1 and L2 auto with rigor; L3/L4 → new Product (no review UI yet); historical offers matched.
- **Scope:**
  - `services/matching/pipeline.py`, `scorer.py`, `review_queue.py` (write-only, no UI).
  - `services/matching/__init__.py` exposing `MatchingService`.
  - `cli/backfill_products.py` — resumable batch runner.
  - Golden set of ≥200 pairs: `tests/fixtures/matching/golden/*.yaml` (bikes + nas_hdd).
  - New test files: `tests/test_matching_extractor.py`, `tests/test_matching_normalizer.py`, `tests/test_matching_l1.py`, `tests/test_matching_l2.py`, `tests/test_matching_negative_evidence.py`.
  - Evaluation script: `cli/eval_matching.py` (reads golden set, prints precision/recall/F1 per layer).
  - Wire `MatchingService` into `services/fetcher.py` so fresh ingest links offers to products.
- **Dependencies:** B.
- **Risks:** **highest in the project** — false merge. DoD gates guard against it.
- **DoD:** on golden set: L1 precision = 1.0; L2 precision ≥ 0.98, recall ≥ 0.70; backfill idempotent (second run = 0 changes); zero orphans; `manual_review_rate` < 30% on golden set.

### Phase D — Product dashboard (MVP)

- **Goal:** `/products` (list) and `/products/{uuid}` (detail with cross-source timeline + active offers).
- **Scope:**
  - `dashboard/routes/products.py` — new APIRouter.
  - `dashboard/services/product_service.py` — query/render logic.
  - `dashboard/schemas.py` — Pydantic models for Product API (`ProductListResponse`, `ProductDetailResponse`, `OfferSummary`, `PricePointSeries`).
  - `dashboard/templates/products_list.html`, `product_detail.html` + a `product_timeline` macro for event rendering.
  - `visualization/charts.py` — new `generate_product_price_chart(product_id, db)` cross-source chart.
  - Sidebar nav gains "Products" tab (shown when `PRODUCT_MODEL_ENABLED=true`).
  - Old `/deals` runs unchanged.
  - New test file: `tests/test_products_routes.py`.
- **Dependencies:** C.
- **Risks:** performance with many offers → indexes on `(product_id, recorded_at)` validated with EXPLAIN.
- **DoD:** Playwright E2E in `tests/e2e/test_products.py`: `/products` → click → product detail with ≥ 2 sources; active offers clickable to external URLs; no regressions in `/deals`.

### Phase E — Manual review queue UI

- **Goal:** handle L3 (and borderline L2) interactively; 7-day undo.
- **Scope:**
  - `dashboard/routes/review.py` — GET list, POST actions (approve, reject, merge, split, skip, undo).
  - `dashboard/services/review_service.py`.
  - `dashboard/schemas.py` — `ReviewAction`, `ReviewActionResponse`.
  - `dashboard/templates/review_queue.html`, `review_item.html` partial.
  - `storage/repositories.py` — `MatchRepository.undo(decision_id)` using `match_decisions.undo_snapshot`.
  - Auto-append `manual_merge_key` alias on approve.
  - New test file: `tests/test_review_flow.py`.
- **Dependencies:** D.
- **Risks:** destructive user actions → undo is mandatory; CSRF middleware already guards POSTs.
- **DoD:** integration flow: proposal → approve → alias → next fetch hits L1; undo restores state; negative evidence prevents re-proposal.

### Phase F — Cutover

- **Goal:** `PRODUCT_MODEL_ENABLED` default on; Telegram + bot + product-level watchlist.
- **Scope:**
  - Default env flag flip.
  - `notifiers/telegram.py` — `build_deal_keyboard` adds "Produkt" deep-link button when `product_id` known.
  - `feedback_bot.py` — new command `/product <uuid>`; `/watch` resolves to `product_id` when available, falls back to `deal_id` (existing subscriptions preserved).
  - `services/alerter.py` — price-drop digest and per-event alerts pull `product_id` into message body.
  - README + CLAUDE.md updates.
- **Dependencies:** D+E stable ≥ 7 days, canary audit green.
- **Risks:** alert regressions — guarded by `tests/test_fx_alert_semantics.py` and `tests/test_feedback_bot.py`.
- **DoD:** flag default-on in prod; feedback bot E2E; 48h of monitoring with no new errors; canary audit precision ≥ 0.98.

### Phase G — Background merge sweep (post-MVP)

- **Goal:** improve recall — re-match products when new aliases have appeared.
- **Scope:** new CLI `cli/reindex_match_candidates.py` as nightly cron; merge/day safety cap; Telegram report.
- **Dependencies:** F stable.
- **DoD:** recall improves, precision holds, zero false-merge incidents.

---

## 6. MVP vs later

### MVP (phases A→D, optionally E without full UI)

- Schema: products/offers/aliases/payload_history/match_reviews/match_decisions.
- Dual-write.
- Extractor: brand, model, size, capacity, EAN/SKU/ceneo_group_id where available.
- Pipeline L1+L2 (with required_match_attrs).
- Conservative backfill fallback.
- NBP currency conversion.
- New views `/products`, `/products/{uuid}` in parallel with `/deals`.

### Next (E→F)

- Manual review queue UI, undo, negative evidence.
- Cutover: Telegram product link, product-level watchlist.

### Post-MVP (G+)

- Background merge sweep.
- ProductFamily as an entity.
- Public API `/api/products`.
- Cross-category matching (deliberately blocked in MVP).

### Nice to have (don't touch without a use case)

- Image-based matching (perceptual hash).
- ML scorer.
- Side-by-side comparator.
- Embeddable widget.

---

## 7. System changes

### ORM & persistence

- `storage/models.py` — rename `Deal` → `Offer` (table `deals` → `offers`); rename `PriceHistory` → `PricePoint` (table `price_history` → `price_points`); new models `Product`, `ProductAlias`, `OfferPayloadHistory`, `DealEvent`, `MatchReview`, `MatchDecision`, `FxRate`. Keep `WatchlistItem`, `Feedback`, `AlertQueue`, `SeenDeal` — their FKs retarget to `offers` via Alembic.
- `storage/repositories.py` — rename `DealRepository` → `OfferRepository` (keep an alias for callers); add `ProductRepository`, `ProductAliasRepository`, `OfferPayloadHistoryRepository`, `DealEventRepository`, `MatchReviewRepository`, `MatchDecisionRepository`, `FxRateRepository`. Extend `PricePointRepository` with `price_pln`, `price_original`, `currency_original`, `fx_rate_used`.
- `storage/migrations/versions/003_rename_deals_to_offers.py` — Alembic revision (Phase A1): table renames (`deals`→`offers`, `price_history`→`price_points`) and index rename only. Column names preserved. FK retargets onto `offers(id)`.
- `storage/migrations/versions/004_products_schema.py` — Alembic revision (Phase A2): column renames on offers/price_points + additive new columns + all new tables + indices + FTS5 triggers.
- No legacy `storage/sqlite.py` module remains in the repo — all persistence already flows through `storage/repositories.py` and `storage/models.py`. Any future external caller still passing the old name should be redirected to the repository classes.

### Service layer

- `services/fetcher.py` — no behavioral change; `DealFetcher.deduplicate()` remains as the in-memory dedup for a single run. Result feeds the matching pipeline, which handles persistent cross-run matching.
- `services/matching/` (new package) — `extractor.py`, `normalizer.py`, `scorer.py`, `pipeline.py`, `review_queue.py`, `candidate_index.py` (FTS5 + rapidfuzz wrapper).
- `services/fx/nbp.py` (new module) — NBP client with `FxRateRepository` cache and fallback-to-last-known.
- `services/types.py` — add `MatchResult`, `OfferPayload`, `ExtractedAttributes` dataclasses; extend `ScoredDeal` with optional `product_id`.
- `services/alerter.py` — insert product deep-link into alert payloads when `product_id` is present.
- `services/price_tracker.py` — compare `price_original` when `currency_original` unchanged across consecutive PricePoints; FX-only moves do not trigger alerts.
- `deal_hunter.py` — orchestration extended: after `DealFetcher.fetch_all()` → for each Deal: upsert Offer → append `OfferPayloadHistory` (FIFO N=10) → extract attributes → match → create/link Product → write PricePoint with FX → emit `DealEvent`.

### Dashboard

- `dashboard/routes/products.py` (new) — `GET /products`, `GET /products/{uuid}`, API endpoints under `/api/products/…` (list, detail, offers, price-history); all reads go through `ProductService`.
- `dashboard/routes/review.py` (new) — `GET /review`, `POST /review/{id}/action`, `POST /products/{uuid}/merge`, `POST /products/{uuid}/split`, `POST /match_decisions/{id}/undo`. Mutating routes remain gated by the existing CSRF middleware in [dashboard/__init__.py](dashboard/__init__.py).
- `dashboard/services/product_service.py` (new) — query/aggregation logic for product list and detail pages.
- `dashboard/services/review_service.py` (new) — review queue operations, merge/split/undo flows.
- `dashboard/schemas.py` — extend with Pydantic v2 schemas: `ProductOut`, `ProductDetailOut`, `ProductOfferOut`, `ReviewItemOut`, `MergeRequestIn`, `SplitRequestIn`.
- `dashboard/routes/deals.py` — surface "View product" link when `Offer.product_id` is set; no semantic change to existing endpoints.
- `dashboard/__init__.py` — register `products` and `review` routers alongside existing ones.
- Templates: new `products_list.html`, `product_detail.html` (timeline + chart + active offers + price points), `review_queue.html`. Add "Products" + "Review" tabs to `base.html` nav.

### CLI

- `cli/backfill_products.py` (new) — one-shot, resumable backfill over existing Offers.
- `cli/eval_matching.py` (new) — compute precision/recall/F1 against golden set under `tests/fixtures/matching/golden/`.
- `cli/verify.py` — no change beyond propagating `product_id` when verbose output shows matches.
- `scripts/fetch_fx_rates.py` (new, one-file script) — daily cron invoking `services/fx/nbp.py`.
- `scripts/reindex_match_candidates.py` (new, phase G) — nightly merge-sweep runner.
- Systemd: add `deal-hunter-fx.timer` (daily 06:00) and `deal-hunter-reindex.timer` (nightly, phase G) under `scripts/systemd/`.

### Stores, profiles, validation

- `stores/*.yaml` — new optional sections `identifiers:` (ean, sku, mpn, canonical_url_pattern, ceneo_group_id) and `attributes:` (per-category selectors).
- `profiles/*.yaml` — new `required_match_attrs:` list; optional `matching:` overrides (thresholds, weights).
- `utils/validation.py` — validate both new sections; fail fast on unknown attribute keys per category registry.
- `sources/base.py` — extend `Deal` dataclass with optional `ean`, `sku`, `mpn`, `brand_hint`, `attributes_hint`. Backward compatible (defaults `None`/`{}`).

### Telegram

- `notifiers/telegram.py` — add a "Product" deep-link button in `send_alert` and `send_price_drop_alert` when `product_id` is available in the alert payload.
- `--digest` path in `deal_hunter.py` — after cutover, groups drops per product rather than per offer.

### Feedback bot

- `feedback_bot.py` — new command `/product <uuid>` (shows product summary + active offers).
- `/watch <deal_id>` continues to accept the legacy `{source}:{native_id}` id; resolves to `product_id` internally when available, falls back to offer-level tracking otherwise.
- Callback_data remains keyed on the stable offer id (`{source}:{native_id}`), preserved verbatim by migration `003`.

---

## 8. Tests and validation

Follow existing naming conventions under `tests/` (flat layout, `test_*.py`) and `tests/e2e/` for Playwright browser tests. Extend existing `test_models.py`, `test_repositories.py`, and `test_services.py` where the new code lives alongside the refactored pieces.

### Unit (`tests/`)

- `test_models.py` (extend) — schema for new ORM models; renamed `Offer`/`PricePoint` tables; FK integrity to `Product`.
- `test_repositories.py` (extend) — `ProductRepository`, `ProductAliasRepository`, `OfferPayloadHistoryRepository` (FIFO N=10 eviction), `DealEventRepository`, `MatchReviewRepository`, `MatchDecisionRepository`, `FxRateRepository`.
- `test_matching_normalizer.py` — lowercase, diacritics, stopwords, separators, size normalization ("58cm" ≡ "58" ≡ "r.58").
- `test_matching_extractor.py` — per source on HTML/JSON fixtures: brand/model/EAN/SKU/attributes, edge cases.
- `test_matching_l1.py` — hard identifiers, idempotency.
- `test_matching_l2.py` — `required_match_attrs` (different size → no merge), token_set_ratio thresholds, null-vs-known (blocks).
- `test_matching_negative_evidence.py` — "sticky no" (MatchDecision.type=negative blocks re-match).
- `test_matching_ceneo_group.py` — `ceneo_group_id` as L2 signal, still gated by `required_match_attrs`.
- `test_fx_nbp.py` — NBP client, cache, fallback-to-last-known, PLN conversion.

### Integration (`tests/`)

- `test_services.py` (extend) — `DealFetcher.deduplicate()` unchanged; matching pipeline consumes deduped result; orchestration in `deal_hunter.py` produces expected `DealEvent` sequence.
- `test_ingest_pipeline_products.py` — full flow: mock source → Offer upsert → payload history → match → Product link → PricePoint (with FX) → DealEvent; idempotent under replay.
- `test_review_flow.py` — L3 → review queue → manual approve → alias created → next fetch hits L1 automatically.
- `test_merge_split_undo.py` — merge two products → split → undo within 7-day window.
- `test_fx_alert_semantics.py` — price-drop alert does NOT fire from FX movement alone when `price_original` and `currency_original` are unchanged.

### Dashboard routes (`tests/`)

- `test_dashboard.py` (extend) — existing dashboard endpoints still pass after adding "View product" link; no regression in deals/health/tuner.
- `test_products_routes.py` — `/products`, `/products/{uuid}`, API endpoints; pagination; filters; Pydantic response schemas.
- `test_review_routes.py` — `/review`, `POST /review/{id}/action`, merge/split/undo; CSRF middleware rejects without `HX-Request` header.

### E2E (`tests/e2e/`)

- `test_products.py` — products list page, product detail page (timeline + active offers table), price chart render.
- `test_review.py` — review queue interaction, approve/reject buttons, product merge/split dialogs.

### Migration tests (`tests/`)

- `test_migration_003_rename.py` (Phase A1, landed) — Alembic `003_rename_deals_to_offers`: seeds legacy `deals`/`price_history`, upgrades, downgrades, re-upgrades, and verifies row data survives intact across the round-trip plus that column names are unchanged (only the table identifier moved).
- `test_migration_004_products_schema.py` (Phase A2) — Alembic `004_products_schema`: idempotency under `upgrade`/`downgrade`/`upgrade`, no data loss, `source_native_id` backfill correctness.
- `test_cli_backfill_products.py` — `cli/backfill_products.py` idempotency, checkpoint recovery, resumable after interruption.

### Match quality

- Golden set ~200 pairs (same/different) per category, `tests/fixtures/matching/golden/*.yaml`.
- Metrics via `scripts/eval_matching.py` — precision, recall, F1, per layer.
- **Gates:**
  - L1 precision = 1.0 (hard).
  - L2 precision ≥ 0.98, recall ≥ 0.70.
  - L3 (review-only): measure `human_accept_rate` after phase E.
- Operational metric in `/health`: `manual_review_rate` (steady-state target < 20%; > 30% → extractor tuning).
- Weekly alert: `false_merge_rate > 0.5%` → cutover gate / rollback.
- Canary: weekly cron samples 20 auto-L2 into `match_reviews.status=audit_sample`.

### Dashboard sanity

- Product with N offers: min/max/median consistent with PricePoint.
- Offer deactivation (`is_active=0`) does not break product price history.
- Cross-source timeline renders when a source has gaps.

---

## 9. Risks and decisions

### Technical risks

- **Low EAN/SKU coverage** in Polish stores (Pepper near zero, Ceneo has `ceneo_group_id` — gold, x-kom inconsistent). L2 carries most of the weight → higher `manual_review_rate`.
- **Cloudflare on x-kom** — store YAML exists, live scraping is sometimes blocked. Product gets created but without fresh offers.
- **Table rename in Alembic (`003`, A1)** — must retarget all existing FKs (watchlist, feedback, price_points, seen_deals keeps its own table) atomically; `render_as_batch=True` in `env.py` handles SQLite's ALTER limits. Run the rename on a copy of a real production DB first and verify `PRAGMA foreign_key_check` clean. Heavier column restructures in `004` (A2) use CREATE new → INSERT SELECT → DROP old → RENAME pattern.
- **NBP API downtime** — cache + fallback to last known rate, warning logged.
- **Regex in profile YAML** (score_rules) and extractor — they do not collide (extractor runs on raw_title before scoring).
- **In-memory vs persistent dedup overlap** — `DealFetcher.deduplicate()` (fuzzy 0.85 + ±5% price) removes duplicates inside a single fetch; the matching pipeline handles identity across runs. Ensure the pipeline does not re-run fuzzy dedup on an already-deduped batch; treat its input as already-representative.

### Product risks

- **False merge erodes alert trust** → rigorous thresholds + required_match_attrs + canary.
- **FX-driven false price drops** → alert threshold on price_original when currency unchanged.
- **Existing user watchlist** — migration must preserve subscriptions (deal_id fallback).
- **"Explosion of products"** — if the extractor is weak, each offer → a new product → cluttered dashboard. Mitigation: metric `products_with_only_one_offer_after_30d` + manual merge.

### Decisions made (during brainstorming)

| # | Decision |
|---|---|
| 1 | `required_match_attrs`: bikes: `{size, frame_color, year}`; nas_hdd: `{capacity_tb, form_factor}`. Other profiles: defined per profile at implementation time. |
| 2 | `ceneo_group_id` as an L2 signal (not L1), still requires `required_match_attrs` agreement. |
| 3 | Price variants on one page → N Offers, suffix `#size=54` in `source_native_id`. |
| 4 | Currencies: NBP conversion to PLN in MVP; price_original + fx_rate_used in PricePoint; alert threshold on price_original when currency unchanged. |
| 5 | Cross-profile matching blocked, hard category barrier. |
| 6 | Product.id = UUID, no slugs. URL: `/products/{uuid}`. |
| 7 | Review queue priority = `score + (temp/20 if Pepper) + (5 if within budget)`. |
| 8 | MVP without Family entity, only `attributes.family_key` (string). |
| 9 | Soft-delete Product after 180 days without an active offer, flag `archived=1`. |
| 10 | `offer_payload_history` as a separate table, N=10 FIFO snapshots per offer. |
| 11 | **Naming refactor (Option B):** rename existing `Deal`/`deals` → `Offer`/`offers` and `PriceHistory`/`price_history` → `PricePoint`/`price_points`; introduce a new `DealEvent` table for the event log. Offer ids (`{source}:{native_id}`) are preserved verbatim so callback_data, watchlist FK, and feedback bot commands keep working. Chosen over a compatibility-shim approach to avoid long-term naming drift. |

### Decisions deferred to implementation (non-blockers)

- `required_match_attrs` for profiles other than bikes and nas_hdd — enumerate current profiles and define per profile.
- NBP fetch frequency — proposed daily at 06:00 (before the first deal-hunter cron).
- FIFO size for OfferPayloadHistory — currently N=10; reduce to N=5 if DB growth becomes an issue.

---

## Recommended rollout order (9 steps)

1. **Table + class rename, column names preserved** (Phase A1) — Alembic `003`, `Deal`→`Offer`, `PriceHistory`→`PricePoint`. Zero caller-visible contract change. *In progress on worktree `phase-a1-rename`.*
2. **Column renames + new schema + dual-write** (Phase A2) — Alembic `004`, new tables, `_to_dict()` emits new keys, dashboard/Telegram/bot adapters migrate in lockstep; ingest appends `offer_payload_history` + emits `deal_events`.
3. **Extractor + NBP FX + `identifiers:` section in stores YAML** (Phase B) — extraction + currency conversion + coverage report.
4. **Pipeline L1 only** (Phase C part 1) — auto-match via hard identifiers; no match → new Product; conservative backfill.
5. **Golden set + metrics + L2 pipeline with required_match_attrs** (Phase C part 2) — precision ≥ 0.98 gate before enabling L2.
6. **Dashboard `/products` read-only** (Phase D) — parallel to `/deals`, cross-source timeline.
7. **Manual review queue + undo** (Phase E) — L3 actionable, audit log, negative evidence.
8. **Cutover: Telegram + bot + product watchlist** (Phase F) — `/products` default, canary audit green.
9. **Background merge sweep** (Phase G, post-MVP) — nightly with safety caps.
