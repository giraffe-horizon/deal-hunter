# Products & Offers — migrating from "deal feed" to "products with pinned offers"

**Date:** 2026-04-13
**Status:** design (approved by user through Q&A dialog)
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

### Entities

- **Product** — canonical representation of a specific variant/SKU (one bike size, one HDD capacity). Carries normalized title, brand, model, structural attributes, review status, last match confidence, audit metadata. Primary key: UUID. No slugs — dashboard URL is `/products/{uuid}`.
- **ProductAlias** — any known external identifier mapping to a Product (EAN, ASIN, MPN, store SKU, canonical URL, `ceneo_group_id`, `manual_merge_key`). Primary carrier of certainty — matcher prefers attaching an alias over dragging title similarity.
- **Offer** — active offer from a single source, identity-stable over time. One URL/`source_native_id` lives for its whole lifecycle; `current_price` and `availability` change. Holds `raw_title`, extracted `attributes_hint`, time metadata.
- **OfferPayloadHistory** — separate table with the last N=10 raw_payload snapshots per Offer (FIFO). Used for debugging and forensics on false merges.
- **Deal** (existing entity, semantic evolution) — point-in-time event/alert: `new_listing`, `price_drop`, `price_increase`, `back_in_stock`, `expiring`. Has FK to Offer and denormalized FK to Product (for fast queries). Format `id = "{source}:{native_id}"` **preserved** (required by feedback_bot callback_data and systemd units).
- **PricePoint** — price point per Offer with cross-source aggregation via `product_id`. Stores `price_pln`, `price_original`, `currency_original`, `fx_rate_used`, `recorded_at`, `availability`.
- **MatchReview** — manual review queue entry: offer without confident match + top-N candidates with confidence + reason + priority.
- **MatchDecision** — audit log of every matcher decision (auto L1/L2/L3, manual approve/reject/split/merge) with the signals that drove it.

### Relationships

- Product 1:N ProductAlias, 1:N Offer, 1:N PricePoint, 1:N Deal
- Offer 1:N Deal (events over time), 1:N PricePoint, 1:N OfferPayloadHistory
- MatchReview N:1 Offer, M:N (suggested) Product

### Price history

- Source of truth: PricePoint per Offer.
- `product_id` denormalized in PricePoint → single query to assemble a cross-source product timeline.
- "Lowest price ever" = MIN(price_pln) WHERE product_id = X.
- Price is **not** a match signal (differs by definition).
- With different original currencies: alert threshold (`min_drop_percent`, `min_drop_amount`) computed on `price_original` when currency has not changed — avoids false alerts driven by FX movement.

---

## 2. Data model (SQLite)

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

### offers

| column | type | notes |
|---|---|---|
| id | INTEGER PK | |
| product_id | TEXT FK | NULL allowed (before match) |
| source | TEXT NOT NULL | |
| source_native_id | TEXT NOT NULL | source id; variants use suffix `#size=54` |
| url | TEXT NOT NULL | |
| raw_title | TEXT NOT NULL | never overwritten |
| current_price_pln | INTEGER | smallest unit (grosz), converted via NBP |
| current_price_original | INTEGER | smallest unit in original currency |
| currency_original | TEXT NOT NULL DEFAULT 'PLN' | |
| fx_rate_used | REAL | NULL for PLN |
| availability | TEXT | `in_stock` \| `out_of_stock` \| `unknown` |
| attributes_hint | JSON | extracted pre-match |
| first_seen_at | TEXT NOT NULL | |
| last_seen_at | TEXT NOT NULL | |
| is_active | INTEGER NOT NULL | 0/1 |

Uniqueness: `UNIQUE (source, source_native_id)`, `UNIQUE (source, url)`. Indexes: `product_id`, `last_seen_at`, `(source, is_active)`.

### offer_payload_history

| column | type | notes |
|---|---|---|
| id | INTEGER PK | |
| offer_id | INTEGER FK NOT NULL | ON DELETE CASCADE |
| raw_payload | JSON NOT NULL | scrape snapshot |
| captured_at | TEXT NOT NULL | ISO |

Retention: max 10 rows per `offer_id`, FIFO. Cleanup inline on every `touch_offer` or via cron.

### deals (extension of existing)

Added columns (all `NULL`-allowed for backward compat):
- `offer_id` INTEGER FK
- `product_id` TEXT FK
- `event_type` TEXT DEFAULT `'new_listing'` — enum: `new_listing` \| `price_drop` \| `price_increase` \| `back_in_stock` \| `expiring`

**Format `id = "{source}:{native_id}"` preserved** (feedback_bot callback_data, systemd, CLI).

### price_history (extension of existing)

Added columns:
- `offer_id` INTEGER FK
- `product_id` TEXT FK
- `price_pln` INTEGER
- `price_original` INTEGER
- `currency_original` TEXT DEFAULT `'PLN'`
- `fx_rate_used` REAL
- `availability` TEXT

Indexes: `(offer_id, recorded_at DESC)`, `(product_id, recorded_at DESC)`.

### match_reviews

| column | type | notes |
|---|---|---|
| id | INTEGER PK | |
| offer_id | INTEGER FK NOT NULL | |
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
| offer_id | INTEGER FK | |
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
- Offer: `source, source_native_id, url, raw_title, currency_original, first_seen_at, last_seen_at, is_active`.
- ProductAlias: `product_id, identifier_type, identifier_value, confidence, created_by, created_at`.
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

Strangler pattern, feature flag `PRODUCT_MODEL_ENABLED`, dual-write, single-read-old → dual-read → cutover.

**Phase 0 — schema only**
- `scripts/migrate_add_products_schema.py` — idempotent: `CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ADD COLUMN` one at a time with try/except.
- No write-path code changes.

**Phase 1 — dual-write Offer**
- Ingest creates/updates Offer and OfferPayloadHistory alongside Deal. Product = NULL.
- User sees nothing.

**Phase 2 — backfill Products**
- `scripts/backfill_products.py` iterates Offers without `product_id`, runs L1+L2 pipeline, creates Product where no match exists.
- Logs to `match_decisions`. Script is resumable (checkpointed per batch).
- After backfill: `offers.product_id` populated ≥ 95%.

**Phase 3 — dual-read dashboard**
- `/products` behind a flag (env / query `?view=products`). `/deals` still default. User compares.

**Phase 4 — cutover**
- `PRODUCT_MODEL_ENABLED=true` becomes default. `/deals` becomes legacy / redirects to `/events`.
- Telegram alerts still per Deal (event), with an extra "Product" button.

**Phase 5 — cleanup (optional, ~1 month later)**
- Remove dead code, legacy templates.

### Backward compatibility (hard guarantees)

- `Deal.id = "{source}:{native_id}"` format preserved — feedback_bot callback_data, CLI `--price-chart "pepper:12345"`, systemd timers — all work unchanged.
- Watchlist: migration adds `product_id` where known, `deal_id` stays. New subscriptions use product level; existing deal-id subscriptions continue to work.
- Old deals without `offer_id`/`product_id`: remain visible as "legacy, unmatched", not hidden.

### Historical data migration

- For each offer: Offer reconstructed from deals aggregation (`first_seen_at = min(deal.created_at)`, `last_seen_at = max(deal.created_at)`, `raw_title = most recent`).
- Price history: preserved where it existed in `price_history`. No reconstruction of prices from deals (accepted).

### Dual-write vs adapter

Dual-write, because writes are infrequent (crons every 30min) and read consistency on both models is critical for cutover confidence.

---

## 5. Implementation phases

### Phase A — Schema + dual-write Offer

- **Goal:** new tables exist; every new ingest creates/refreshes Offer + OfferPayloadHistory.
- **Scope:** schema migration; `storage/sqlite.py` (new methods `upsert_offer`, `touch_offer`, `append_payload_history`, N=10 cleanup); hook in ingest pipeline in `deal_hunter.py`.
- **Dependencies:** none.
- **Risks:** SQLite migrations (ALTER), concurrent-cron write integrity.
- **DoD:** integration tests: new deal → Offer row; `UNIQUE` constraints hold; old flow unchanged; migration rollback tested; OfferPayloadHistory capped at N=10.

### Phase B — Attribute + identifier extractor + FX

- **Goal:** for every offer we extract `brand, model, attributes_hint` and where available `ean, sku, canonical_url, mpn, ceneo_group_id`. NBP fetcher works.
- **Scope:** new module `matching/extractor.py` + `matching/normalizer.py`. Extend `stores/*.yaml` with `identifiers:` and `attributes:` sections. Validation in `utils/validation.py`. Module `fx/nbp.py` + cron `scripts/fetch_fx_rates.py`.
- **Dependencies:** A.
- **Risks:** low EAN/SKU coverage → L2 must carry the weight; NBP API downtime → fallback to last rate.
- **DoD:** per-source tests on HTML/JSON fixtures; identifier coverage report per source in logs; `brand+model` coverage ≥ 80% on the tagged test set; NBP rate cached in DB, fallback tested.

### Phase C — Matching pipeline + Product creation

- **Goal:** L1 and L2 auto with rigor; L3/L4 → new Product (no review UI yet).
- **Scope:** `matching/pipeline.py`, `matching/scorer.py`, `matching/review_queue.py` (write-only, no UI). Golden set of 200 pairs (bikes + nas_hdd). `scripts/eval_matching.py`. Backfill.
- **Dependencies:** B.
- **Risks:** **highest in the project** — false merge. DoD gates guard against it.
- **DoD:** on golden set: L1 precision = 1.0; L2 precision ≥ 0.98, recall ≥ 0.70; backfill idempotent (second run = 0 changes); zero orphans; `manual_review_rate` < 30% on golden set.

### Phase D — Product dashboard (MVP)

- **Goal:** `/products` (list) and `/products/{uuid}` (detail with cross-source timeline + active offers).
- **Scope:** routes in `dashboard.py`, templates `products_list.html`, `product_detail.html`. Reuse + extend `visualization/charts.py` with a cross-source price chart. Old `/deals` runs in parallel.
- **Dependencies:** C.
- **Risks:** performance with many offers → indexes on `(product_id, recorded_at)`.
- **DoD:** Playwright E2E: `/products` → click → product detail with ≥ 2 sources; active offers clickable to external URLs; no regressions in `/deals`.

### Phase E — Manual review queue UI

- **Goal:** handle L3 (and borderline L2) interactively; 7-day undo.
- **Scope:** `/review` endpoint + template + POST actions; `match_decisions.undo_snapshot`; auto-append `manual_merge_key` to `product_aliases` on approve.
- **Dependencies:** D.
- **Risks:** destructive user actions → undo is mandatory.
- **DoD:** integration flow: proposal → approve → alias → next fetch hits L1; undo restores state; negative evidence prevents re-proposal.

### Phase F — Cutover

- **Goal:** `/products` default; Telegram + bot + product-level watchlist.
- **Scope:** routing, `notifiers/telegram.py` ("Product" deep-link button), `feedback_bot.py` (`/product <id>`, `/watch` uses product_id when available, falls back to deal_id), docs.
- **Dependencies:** D+E stable ≥ 7 days, canary audit green.
- **Risks:** alert regressions.
- **DoD:** flag on in prod; feedback bot E2E; 48h of monitoring with no new errors; canary audit precision ≥ 0.98.

### Phase G — Background merge sweep (post-MVP)

- **Goal:** improve recall — re-match products when new aliases have appeared.
- **Scope:** nightly cron `scripts/reindex_match_candidates.py`, merge/day safety cap, Telegram report.
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

### Backend

- `storage/sqlite.py` — new CRUD for products/offers/aliases/payload_history/match_reviews/match_decisions; extended `price_history` methods (price_pln, price_original, fx).
- `deal_hunter.py` — after `fetch_deals` a new pipeline: upsert Offer → append payload history → extractor → match → create/link Product → write PricePoint (with FX) → decide event_type → write Deal.
- `matching/` (new module) — `extractor.py`, `normalizer.py`, `scorer.py`, `pipeline.py`, `review_queue.py`.
- `fx/nbp.py` (new module) — NBP client with cache and fallback.
- `stores/*.yaml` — new sections `identifiers:` (ean, sku, mpn, canonical_url_pattern, ceneo_group_id) and `attributes:` (per-category selectors).
- `profiles/*.yaml` — new `required_match_attrs:` field (list of strings).
- `utils/validation.py` — validate new sections.
- `sources/base.py` — `Deal` gains optional `ean, sku, mpn, brand_hint, attributes_hint` (backward compatible).

### Dashboard

- `dashboard.py` — new routes: `GET /products`, `GET /products/{uuid}`, `GET /api/products`, `GET /api/products/{uuid}`, `GET /api/products/{uuid}/offers`, `GET /api/products/{uuid}/price-history`, `GET /review`, `POST /review/{id}/action`, `POST /products/{uuid}/merge`, `POST /products/{uuid}/split`, `POST /match_decisions/{id}/undo`.
- New templates: `products_list.html`, `product_detail.html` (timeline + chart + active offers table + price history), `review_queue.html`.
- Existing deals templates: "View product" link wherever `product_id` is known.
- Navigation: new "Products" tab.

### Jobs

- `scripts/migrate_add_products_schema.py` — one-shot migration.
- `scripts/backfill_products.py` — one-shot backfill, resumable.
- `scripts/eval_matching.py` — compute metrics on golden set.
- `scripts/fetch_fx_rates.py` — daily cron (NBP).
- `scripts/reindex_match_candidates.py` — nightly cron (phase G).

### Telegram

- `notifiers/telegram.py` — add a "Product" deep-link button in `send_alert` and `send_price_drop_alert`.
- Digest `--digest` — after cutover groups price drops per product.

### Feedback bot

- New command `/product <uuid>`.
- `/watch <deal_id>` works internally on `product_id` where available; fallback to deal_id.
- Callback_data unchanged (key: deal_id).

---

## 8. Tests and validation

### Unit

- `test_normalizer.py` — lowercase, diacritics, stopwords, separators, size normalization ("58cm" ≡ "58" ≡ "r.58").
- `test_extractor.py` — per source on HTML/JSON fixtures: brand/model/EAN/SKU/attributes, edge cases.
- `test_matcher_l1.py` — hard identifiers, idempotency.
- `test_matcher_l2.py` — required_match_attrs (different size → no merge), token_set_ratio thresholds, null-vs-known (blocks).
- `test_matcher_negative_evidence.py` — "sticky no".
- `test_ceneo_group.py` — ceneo_group_id as L2 + required_match_attrs is required.
- `test_fx_nbp.py` — NBP client, cache, fallback, conversion.

### Integration

- `test_ingest_pipeline_products.py` — full flow: mock source → offer → match → product → deal event; idempotency.
- `test_review_flow.py` — L3 → review → manual approve → alias created → next fetch hits L1.
- `test_merge_split_undo.py` — merge → split → undo within 7 days.
- `test_dashboard_products.py` — list/detail/API endpoints; pagination; filters; Playwright E2E.
- `test_fx_alert_semantics.py` — price-drop alert does NOT fire from FX movement alone when original currency has unchanged price.

### Migration tests

- `test_migration_schema.py` — on a copy of real DB: migration idempotency, counts, no data loss.
- `test_backfill_products.py` — backfill idempotency, checkpoint recovery.

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
- **SQLite ALTER migrations** — prefer `ADD COLUMN` one at a time; heavier changes: CREATE new → INSERT SELECT → DROP old → RENAME.
- **NBP API downtime** — cache + fallback to last known rate, warning logged.
- **Regex in profile YAML** (score_rules) and extractor — they do not collide (extractor runs on raw_title before scoring).

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

### Decisions deferred to implementation (non-blockers)

- `required_match_attrs` for profiles other than bikes and nas_hdd — enumerate current profiles and define per profile.
- NBP fetch frequency — proposed daily at 06:00 (before the first deal-hunter cron).
- FIFO size for OfferPayloadHistory — currently N=10; reduce to N=5 if DB growth becomes an issue.

---

## Recommended rollout order (8 steps)

1. **Schema + dual-write Offer + payload history** (Phase A) — tables + migration + parallel writes.
2. **Extractor + NBP FX + `identifiers:` section in stores YAML** (Phase B) — extraction + currency conversion + coverage report.
3. **Pipeline L1 only** — auto-match via hard identifiers; no match → new Product; conservative backfill.
4. **Golden set + metrics + L2 pipeline with required_match_attrs** (Phase C part 2) — precision ≥ 0.98 gate before enabling L2.
5. **Dashboard `/products` read-only** (Phase D) — parallel to `/deals`, cross-source timeline.
6. **Manual review queue + undo** (Phase E) — L3 actionable, audit log, negative evidence.
7. **Cutover: Telegram + bot + product watchlist** (Phase F) — `/products` default, canary audit green.
8. **Background merge sweep** (Phase G, post-MVP) — nightly with safety caps.
