# Products & Offers — przejście z modelu "feed okazji" na "produkty + oferty"

**Data:** 2026-04-13
**Status:** design (zatwierdzony przez usera po dialogu pytanie-po-pytaniu)
**Cel:** ewolucyjne przekształcenie deal-huntera z dashboardu okazji (per-Deal) w dashboard produktowy (per-Product) z historią cen cross-source i pinowanymi ofertami.

## Kontekst

Obecnie deal-hunter zbiera okazje głównie z Peppera, Ceneo i kilku sklepów YAML (proshop, x-kom, morele) oraz RSS Allegro. Każda okazja to rekord `Deal` z unikalnym `id = "{source}:{native_id}"`. Dashboard pokazuje listę tych dealów jako feed.

Docelowy model:
- ten sam produkt z różnych źródeł jest zgrupowany,
- produkt ma swoją historię ceny cross-source,
- produkt ma wiele aktywnych ofert z linkami,
- obecne "deals" stają się **eventami** (new_listing, price_drop, back_in_stock) podpiętymi do produktu.

**Główne ryzyko projektowe:** entity resolution. False merge (scalenie dwóch różnych produktów w jeden) jest gorszy niż brak merge (pozostawienie osobno). Matching musi być konserwatywny i warstwowy.

## Zasady

- Ewolucja, nie rewrite. Strangler pattern z feature flagą `PRODUCT_MODEL_ENABLED`.
- False merge > brak merge: progi auto-merge wysokie (0.90+ dla L2), `required_match_attrs` per kategoria jako twarda blokada.
- Rozdzielamy **raw/source-specific title** (w Offer/Deal, nigdy nie nadpisywane) od **normalized title** (w Product, generowany przez normalizer).
- Wariant = osobny Product. Family odkładamy (tylko string-field `attributes.family_key`).
- Matching ograniczony do jednej `category` (jedna twarda bariera cross-profile).

---

## 1. Architektura domenowa

### Encje

- **Product** — kanoniczna reprezentacja konkretnego wariantu/SKU (jeden rozmiar roweru, jedna pojemność HDD). Nosi znormalizowany tytuł, markę, model, atrybuty strukturalne, status review, confidence ostatniego matchu, metadane audytowe. Primary key: UUID. Bez slugów, URL w dashboardzie to `/products/{uuid}`.
- **ProductAlias** — każdy znany identyfikator zewnętrzny mapujący na Product (EAN, ASIN, MPN, SKU sklepu, canonical URL, `ceneo_group_id`, `manual_merge_key`). Główny nośnik pewności — matcher woli dokleić alias niż przeciągać tytuł.
- **Offer** — aktywna oferta z jednego źródła, tożsamościowo stabilna w czasie. Jeden URL/`source_native_id` przez cały cykl życia, zmienia się `current_price` i `availability`. Trzyma `raw_title`, extracted `attributes_hint`, metadane czasowe.
- **OfferPayloadHistory** — osobna tabela z ostatnimi N=10 snapshotami raw_payload per Offer (FIFO). Do debugowania i forensyki przy false merge.
- **Deal** (istniejąca encja, ewolucja semantyczna) — zdarzenie punktowe/alert: `new_listing`, `price_drop`, `price_increase`, `back_in_stock`, `expiring`. Ma FK do Offer i denormalizowane FK do Product (dla szybkich query). Format `id = "{source}:{native_id}"` **zachowany** (wymagane przez feedback_bot callback_data i systemd).
- **PricePoint** — punkt ceny per Offer z cross-source agregacją przez `product_id`. Przechowuje `price_pln`, `price_original`, `currency_original`, `fx_rate_used`, `recorded_at`, `availability`.
- **MatchReview** — element kolejki ręcznej weryfikacji: offer bez pewnego matchu + top-N kandydatów z confidence + reason + priority.
- **MatchDecision** — log audytowy każdej decyzji matchera (auto L1/L2/L3, manual approve/reject/split/merge) z sygnałami które zadecydowały.

### Relacje

- Product 1:N ProductAlias, 1:N Offer, 1:N PricePoint, 1:N Deal
- Offer 1:N Deal (eventy w czasie), 1:N PricePoint, 1:N OfferPayloadHistory
- MatchReview N:1 Offer, M:N (suggested) Product

### Historia cen

- Source of truth: PricePoint per Offer.
- Denormalizacja `product_id` w PricePoint → jednym query składamy cross-source timeline produktu.
- "Najniższa cena kiedykolwiek" = MIN(price_pln) WHERE product_id = X.
- Cena **nie jest** sygnałem matchu (różna z definicji).
- Przy różnych walutach oryginalnych: próg alertu (`min_drop_percent`, `min_drop_amount`) liczymy na `price_original` gdy waluta się nie zmieniła — unikamy false alertów z ruchu kursu FX.

---

## 2. Model danych (SQLite)

### products

| pole | typ | uwagi |
|---|---|---|
| id | TEXT PK | UUID v4 |
| canonical_title | TEXT NOT NULL | znormalizowany |
| brand | TEXT | nullable, indexed |
| model | TEXT | nullable, indexed |
| category | TEXT NOT NULL | spójne z profile (bikes, nas_hdd, ...) |
| attributes | JSON NOT NULL | {size, frame_color, year, capacity_tb, form_factor, family_key, ...} |
| canonical_image_url | TEXT | |
| review_status | TEXT NOT NULL | enum: `auto` \| `confirmed` \| `needs_review` \| `rejected` |
| confidence_score | REAL | ostatni score matchu który to utworzył |
| merged_from | JSON | lista id produktów zmerge'owanych w ten (audit) |
| archived | INTEGER NOT NULL DEFAULT 0 | soft-delete |
| created_at | TEXT NOT NULL | ISO |
| updated_at | TEXT NOT NULL | ISO |

Indeksy: `(brand, model)`, `(category)`, FTS5 na `canonical_title`, `(archived, updated_at)`.

### product_aliases

| pole | typ | uwagi |
|---|---|---|
| id | INTEGER PK | |
| product_id | TEXT FK NOT NULL | ON DELETE CASCADE |
| identifier_type | TEXT NOT NULL | enum: `ean` \| `asin` \| `mpn` \| `sku` \| `canonical_url` \| `source_native_id` \| `ceneo_group_id` \| `manual_merge_key` |
| identifier_value | TEXT NOT NULL | |
| source | TEXT | NULL dla globalnych (ean/asin/mpn) |
| confidence | REAL NOT NULL | |
| created_by | TEXT NOT NULL | `auto` \| `manual` |
| created_at | TEXT NOT NULL | |

Unikalność: `UNIQUE (identifier_type, identifier_value, COALESCE(source, ''))`. Indeks na `product_id`.

### offers

| pole | typ | uwagi |
|---|---|---|
| id | INTEGER PK | |
| product_id | TEXT FK | NULL dozwolone (przed matchem) |
| source | TEXT NOT NULL | |
| source_native_id | TEXT NOT NULL | id ze źródła, dla wariantów z suffixem `#size=54` |
| url | TEXT NOT NULL | |
| raw_title | TEXT NOT NULL | nigdy nie nadpisywane |
| current_price_pln | INTEGER | grosze, konwersja z NBP |
| current_price_original | INTEGER | grosze/centów w oryginalnej walucie |
| currency_original | TEXT NOT NULL DEFAULT 'PLN' | |
| fx_rate_used | REAL | NULL dla PLN |
| availability | TEXT | `in_stock` \| `out_of_stock` \| `unknown` |
| attributes_hint | JSON | wyekstraktowane przed matchem |
| first_seen_at | TEXT NOT NULL | |
| last_seen_at | TEXT NOT NULL | |
| is_active | INTEGER NOT NULL | 0/1 |

Unikalność: `UNIQUE (source, source_native_id)`, `UNIQUE (source, url)`. Indeksy: `product_id`, `last_seen_at`, `(source, is_active)`.

### offer_payload_history

| pole | typ | uwagi |
|---|---|---|
| id | INTEGER PK | |
| offer_id | INTEGER FK NOT NULL | ON DELETE CASCADE |
| raw_payload | JSON NOT NULL | snapshot scrape'a |
| captured_at | TEXT NOT NULL | ISO |

Retencja: max 10 rekordów per `offer_id`, FIFO. Cleanup inline przy każdym `touch_offer` lub w cron.

### deals (rozszerzenie istniejącej)

Dodawane kolumny (wszystkie `NULL` dozwolone dla backward compat):
- `offer_id` INTEGER FK
- `product_id` TEXT FK
- `event_type` TEXT DEFAULT `'new_listing'` — enum: `new_listing` \| `price_drop` \| `price_increase` \| `back_in_stock` \| `expiring`

**Format `id = "{source}:{native_id}"` zachowany** (callback_data feedback_bota, systemd, CLI).

### price_history (rozszerzenie istniejącej)

Dodawane kolumny:
- `offer_id` INTEGER FK
- `product_id` TEXT FK
- `price_pln` INTEGER
- `price_original` INTEGER
- `currency_original` TEXT DEFAULT `'PLN'`
- `fx_rate_used` REAL
- `availability` TEXT

Indeksy: `(offer_id, recorded_at DESC)`, `(product_id, recorded_at DESC)`.

### match_reviews

| pole | typ | uwagi |
|---|---|---|
| id | INTEGER PK | |
| offer_id | INTEGER FK NOT NULL | |
| candidate_product_id | TEXT FK | NULL gdy brak kandydata |
| suggested_products | JSON | top-N kandydatów z confidence |
| best_confidence | REAL | |
| reason | TEXT | np. `"fuzzy_only:brand_unknown"`, `"L2_borderline:size_null_on_candidate"` |
| status | TEXT NOT NULL | `pending` \| `approved` \| `rejected` \| `auto_resolved` \| `superseded` \| `audit_sample` |
| priority | INTEGER NOT NULL | wyliczony: `score + (temp/20 jeśli Pepper) + (5 jeśli w budżecie)` |
| decided_by | TEXT | |
| decided_at | TEXT | |
| created_at | TEXT NOT NULL | |

Indeksy: `(status, priority DESC)`, `offer_id`.

### match_decisions (audit log)

| pole | typ | uwagi |
|---|---|---|
| id | INTEGER PK | |
| offer_id | INTEGER FK | |
| product_id | TEXT FK | |
| decision_type | TEXT NOT NULL | `auto_hard_id` \| `auto_strong` \| `auto_fuzzy` \| `manual_approve` \| `manual_reject` \| `manual_split` \| `manual_merge` |
| confidence | REAL | |
| signals | JSON | sygnały które zadecydowały (co matchnęło, co odrzuciło) |
| actor | TEXT NOT NULL | `auto` \| nazwa użytkownika (na razie `"local"`) |
| created_at | TEXT NOT NULL | |
| undo_snapshot | JSON | snapshot pre-change dla undo w oknie 7 dni |

Indeksy: `(offer_id)`, `(product_id)`, `(created_at)`.

### fx_rates

| pole | typ | uwagi |
|---|---|---|
| currency | TEXT PK | kod waluty (EUR, USD, ...) |
| rate_to_pln | REAL NOT NULL | kurs |
| fetched_at | TEXT NOT NULL | ISO |
| table_no | TEXT | numer tabeli NBP (audit) |

Aktualizacja: cron `scripts/fetch_fx_rates.py` raz dziennie. Fallback przy downtime: używamy ostatniego rekordu z logiem ostrzeżenia gdy `fetched_at` > 48h.

### Pola obowiązkowe (walidacja wejściowa)

- Product: `id, canonical_title, category, attributes, review_status, created_at, updated_at`.
- Offer: `source, source_native_id, url, raw_title, currency_original, first_seen_at, last_seen_at, is_active`.
- ProductAlias: `product_id, identifier_type, identifier_value, confidence, created_by, created_at`.
- MatchDecision: `decision_type, actor, created_at` (oraz jeden z `offer_id`/`product_id`).

---

## 3. Strategia matchowania

### Pipeline

Idzie od najsilniejszego do najsłabszego, zatrzymuje się na pierwszej decyzji.

**L1 — Twarde identyfikatory (confidence = 1.0, auto-match, bez review)**
- Offer ma EAN/ASIN/MPN, istnieje ProductAlias o takiej wartości → match.
- Canonical URL offer'a pasuje do `canonical_url` w ProductAlias (per source) → match.
- `(source, source_native_id)` już znane → match idempotentny (kolejny refresh).
- Brak manualnego `manual_reject` w match_decisions dla tej pary (negative evidence).

**L2 — Mocne dopasowanie (confidence 0.85–0.98)**
- Wymaga niepustego `brand` i `model` w `attributes_hint`.
- Wymaga 100% zgodności `required_match_attrs` dla kategorii (patrz poniżej).
- Klucz blokujący: `(brand, model, category)` — zawęża kandydatów.
- Metryka: `token_set_ratio` znormalizowanego tytułu (rapidfuzz) ≥ 0.90.
- **`ceneo_group_id` jako sygnał L2** (nie L1) — jeśli Ceneo zgrupowało X z grupą Y, traktujemy to jak mocny sygnał, ale nadal wymaga zgodności `required_match_attrs`. Confidence bazowa 0.92.
- Próg auto: ≥ 0.90 i zero sprzeczności → auto-match.
- 0.85–0.90 → kolejka review.
- Sprzeczność wartości w `required_match_attrs` (obie strony wypełnione i różne) → **brak matchu, nie review** — tworzymy nowy Product.
- Null po jednej stronie `required_match_attrs` → **brak matchu, nie review** (nie rozluźniamy dla atrybutów obligatoryjnych).

**L3 — Słabe dopasowanie (confidence 0.60–0.84)**
- FTS5 + rapidfuzz na korpusie, brak pewnego brand/model.
- Zawsze kolejka review, nigdy auto-merge.
- Zapisujemy top-3 kandydatów w `suggested_products`.

**L4 — Brak matchu (confidence < 0.60)**
- Tworzymy nowy Product z `attributes_hint`, `review_status = auto`.
- Post-MVP: background sweep okresowo re-matchuje te produkty.

### required_match_attrs per kategoria

Deklaratywne w profile YAML jako `required_match_attrs:`:

- **bikes**: `size`, `frame_color`, `year`
- **nas_hdd**: `capacity_tb`, `form_factor`

Dla innych profili (nieustalone w tym momencie) — ustalane per profil przy implementacji. Walidator `utils/validation.py` wymaga zdefiniowania listy (może być pusta — ale świadomie).

### Reguły merge vs no-merge

- Sprzeczność `required_match_attrs` **zawsze blokuje** merge (nawet przy token_set_ratio 1.0).
- Auto-merge wymaga confidence ≥ 0.90; auto-split nie istnieje (tylko manualny).
- Negative evidence ("sticky no"): para `(offer_id, product_id)` z manualnym `reject` nie jest więcej proponowana.
- Cena i source nie są sygnałami matchu.
- Cross-category matching zablokowany (twarda bariera).

### Warianty

- Wariant = osobny Product. Konserwatywnie.
- N Offerów per wariant gdy strona sklepu ma jeden URL z selectorem rozmiaru. Suffix w `source_native_id`: `proshop:12345#size=54`, `proshop:12345#size=56`.
- Grupowanie rodziny: `attributes.family_key` (string wyliczany z brand+model+year). Encja `ProductFamily` poza MVP.

### Obrona przed false merge

- Wysokie progi auto (L2 ≥ 0.90 + 100% required attrs).
- Canary audit: co tydzień sampluj 20 auto-L2 matchów do `match_reviews` ze statusem `audit_sample` do manualnego przeglądu. Metryka `precision@L2`.
- Alert tygodniowy gdy `false_merge_rate > 0.5%` → gate na cutover.
- Undo dla każdej decyzji w oknie 7 dni — `match_decisions.undo_snapshot` przywraca stan products + aliases.

### Manual review queue

- Widok `/review` sortowany po `priority DESC`.
- Priority = `deal_score + (temperature/20 jeśli Pepper) + (5 jeśli w budżecie)`.
- Dla każdego wpisu: offer (raw_title, zdjęcie, cena, źródło) + top-3 kandydatów z confidence + akcje: `approve_as`, `reject_create_new`, `merge_products`, `skip`.
- Każda decyzja → `match_decisions` + opcjonalne nowe `product_aliases` typu `manual_merge_key` (next time L1 match).

### Konwersja walut (nowe w MVP)

- Kurs NBP pobierany raz dziennie (endpoint `https://api.nbp.pl/api/exchangerates/tables/A/`).
- Cache w SQLite: nowa tabela `fx_rates (currency TEXT PK, rate_to_pln REAL, fetched_at TEXT, table_no TEXT)`. Fallback: ostatni znany kurs gdy NBP down, z logiem ostrzeżenia.
- PricePoint zapisuje `price_original` + `currency_original` + `price_pln` + `fx_rate_used`.
- Alert price_drop liczony na `price_original` gdy waluta się nie zmieniła (uniknięcie false alertów z FX). Jeśli waluta się zmieniła (rzadkie) — liczymy na `price_pln` z notą w audit.

---

## 4. Plan migracji

Strangler pattern, feature flag `PRODUCT_MODEL_ENABLED`, dual-write, single-read-old → dual-read → cutover.

**Faza 0 — schema tylko**
- `scripts/migrate_add_products_schema.py` — idempotentny: `CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ADD COLUMN` pojedynczo z try/except.
- Zero zmian w kodzie pisania.

**Faza 1 — dual-write Offer**
- Ingest tworzy/aktualizuje Offer i OfferPayloadHistory równolegle z Deal. Product = NULL.
- User nic nie widzi.

**Faza 2 — backfill Products**
- `scripts/backfill_products.py` iteruje po Offer bez `product_id`, uruchamia L1+L2 pipeline, tworzy Product tam gdzie brak matchu.
- Log do `match_decisions`. Skrypt wznawialny (checkpoint po batchach).
- Po backfillu: `offers.product_id` wypełnione ≥ 95%.

**Faza 3 — dual-read dashboard**
- `/products` za flagą (env / query `?view=products`). `/deals` nadal domyślny. User porównuje.

**Faza 4 — cutover**
- `PRODUCT_MODEL_ENABLED=true` default. `/deals` jako legacy/redirect do `/events`.
- Telegram alert nadal per Deal (event), z dodatkowym przyciskiem "Produkt".

**Faza 5 — cleanup (opcjonalne, po ~1 miesiącu)**
- Usunięcie martwego kodu, legacy templatów.

### Kompatybilność wsteczna (twarde gwarancje)

- Format `Deal.id = "{source}:{native_id}"` zachowany — feedback_bot callback_data, CLI `--price-chart "pepper:12345"`, systemd timery — działają bez zmian.
- Watchlista: migracja dopisuje `product_id` (gdzie znane), `deal_id` zostaje. Nowe obserwowanie na poziomie produktu, stare na poziomie deal_id nadal działa.
- Stare deale bez `offer_id`/`product_id`: dalej widoczne jako "legacy, unmatched", nie ukrywane.

### Migracja danych historycznych

- Dla każdej oferty: Offer odtworzona z agregacji deals (`first_seen_at = min(deal.created_at)`, `last_seen_at = max(deal.created_at)`, `raw_title = najnowszy`).
- Historia cen: zachowana tam gdzie była w `price_history`. Brak rekonstrukcji cen z dealów (akceptujemy).

### Dual-write vs adapter

Dual-write, bo zapis jest rzadki (crony co 30min), a spójność odczytu na obu modelach krytyczna dla pewności cutoveru.

---

## 5. Etapy implementacji

### Faza A — Schema + dual-write Offer

- **Cel:** nowe tabele istnieją, każdy nowy ingest tworzy/odświeża Offer + OfferPayloadHistory.
- **Zakres:** migracja schema; `storage/sqlite.py` (nowe metody `upsert_offer`, `touch_offer`, `append_payload_history`, cleanup N=10); hook w ingest pipeline w `deal_hunter.py`.
- **Zależności:** brak.
- **Ryzyka:** migracje SQLite (ALTER), integralność przy równoczesnych crony.
- **DoD:** testy integracyjne: new deal → Offer record; `UNIQUE` constraints; stare flow niezmienione; rollback migracji przetestowany; OfferPayloadHistory ograniczona do N=10.

### Faza B — Extractor atrybutów + identyfikatorów + FX

- **Cel:** dla każdej offery ekstraktujemy `brand, model, attributes_hint` i gdzie się da `ean, sku, canonical_url, mpn, ceneo_group_id`. NBP fetcher działa.
- **Zakres:** nowy moduł `matching/extractor.py` + `matching/normalizer.py`. Rozszerzenie `stores/*.yaml` o sekcje `identifiers:` i `attributes:`. Walidacja w `utils/validation.py`. Moduł `fx/nbp.py` + `scripts/fetch_fx_rates.py` cron.
- **Zależności:** A.
- **Ryzyka:** niskie pokrycie EAN/SKU → L2 musi unieść ciężar; NBP API downtime → fallback na ostatni kurs.
- **DoD:** testy per źródło na fixtureach; raport pokrycia identyfikatorami per source w logach; pokrycie `brand+model` ≥ 80% na tagged testset; NBP rate cache w DB, test fallback.

### Faza C — Pipeline matchowania + tworzenie Product

- **Cel:** L1 i L2 auto z rygorem; L3/L4 → nowy Product (bez UI review jeszcze).
- **Zakres:** `matching/pipeline.py`, `matching/scorer.py`, `matching/review_queue.py` (zapis bez UI). Golden set 200 par (bikes + nas_hdd). `scripts/eval_matching.py`. Backfill.
- **Zależności:** B.
- **Ryzyka:** **najwyższe w projekcie** — false merge. Gate przed DoD.
- **DoD:** golden set: L1 precision = 1.0; L2 precision ≥ 0.98, recall ≥ 0.70; backfill idempotentny (drugi run = 0 zmian); zero orphanów; manual_review_rate < 30% na golden set.

### Faza D — Dashboard produktowy (MVP)

- **Cel:** `/products` (lista) i `/products/{uuid}` (detail z cross-source timeline + aktywne oferty).
- **Zakres:** routes w `dashboard.py`, templaty `products_list.html`, `product_detail.html`. Reuse + rozszerzenie `visualization/charts.py` o cross-source price chart. Stary `/deals` działa równolegle.
- **Zależności:** C.
- **Ryzyka:** performance przy wielu ofertach → indeksy na `(product_id, recorded_at)`.
- **DoD:** E2E Playwright: `/products` → klik → product detail z ≥ 2 źródłami; aktywne oferty klikalne do zewnętrznych URLi; zero regresji w `/deals`.

### Faza E — Manual review queue UI

- **Cel:** obsługa L3 (i borderline L2) przez użytkownika; undo w 7-dniowym oknie.
- **Zakres:** `/review` endpoint + templat + akcje POST; `match_decisions.undo_snapshot`; automatyczne dopisywanie `manual_merge_key` do `product_aliases` przy approve.
- **Zależności:** D.
- **Ryzyka:** destrukcyjne akcje usera → undo obowiązkowy.
- **DoD:** flow integracyjny: propozycja → approve → alias → kolejny fetch w L1; undo przywraca stan; negative evidence blokuje powtórną propozycję.

### Faza F — Cutover

- **Cel:** `/products` jako default, Telegram+bot+watchlista produktowa.
- **Zakres:** routing, `notifiers/telegram.py` (przycisk "Produkt" z deeplinkiem), `feedback_bot.py` (`/product <id>`, `/watch` na product_id gdzie dostępne, fallback na deal_id), docs.
- **Zależności:** D+E stabilne ≥ 7 dni, canary audit OK.
- **Ryzyka:** regresje w alertach.
- **DoD:** flag on na prod; feedback bot E2E; monitoring 48h bez nowych błędów; canary audit precision ≥ 0.98.

### Faza G — Background merge sweep (post-MVP)

- **Cel:** poprawa recall — re-match produktów gdy pojawiły się nowe aliasy.
- **Zakres:** cron nightly `scripts/reindex_match_candidates.py`, limit merge/day (bezpieczeństwo), raport Telegram.
- **Zależności:** F stabilne.
- **DoD:** recall rośnie, precision utrzymana, zero incydentów false merge.

---

## 6. MVP vs później

### MVP (fazy A→D, opcjonalnie E bez pełnego UI)

- Schema products/offers/aliases/payload_history/match_reviews/match_decisions.
- Dual-write.
- Extractor: brand, model, size, capacity, EAN/SKU/ceneo_group_id gdzie dostępne.
- Pipeline L1+L2 (z required_match_attrs).
- Backfill z konserwatywnym fallbackiem.
- Konwersja walut NBP.
- Nowe widoki `/products`, `/products/{uuid}` równolegle do `/deals`.

### Następnie (E→F)

- Manual review queue z UI, undo, negative evidence.
- Cutover: Telegram link do produktu, watchlista produktowa.

### Post-MVP (G+)

- Background merge sweep.
- ProductFamily jako encja.
- Publiczne API `/api/products`.
- Cross-category matching (świadomie zablokowane w MVP).

### Nice to have (bez use case nie ruszać)

- Image-based matching (perceptual hash).
- ML scorer.
- Porównywarka side-by-side.
- Embeddable widget.

---

## 7. Zmiany w systemie

### Backend

- `storage/sqlite.py` — nowe CRUD dla products/offers/aliases/payload_history/match_reviews/match_decisions; rozszerzone metody `price_history` (price_pln, price_original, fx).
- `deal_hunter.py` — po `fetch_deals` nowy pipeline: upsert Offer → append payload history → extractor → match → create/link Product → zapis PricePoint (z FX) → decyzja event_type → zapis Deal.
- `matching/` (nowy moduł) — `extractor.py`, `normalizer.py`, `scorer.py`, `pipeline.py`, `review_queue.py`.
- `fx/nbp.py` (nowy moduł) — NBP client z cache i fallback.
- `stores/*.yaml` — nowe sekcje `identifiers:` (ean, sku, mpn, canonical_url_pattern, ceneo_group_id) i `attributes:` (per-kategoria selectory).
- `profiles/*.yaml` — nowe pole `required_match_attrs:` (lista stringów).
- `utils/validation.py` — walidacja nowych sekcji.
- `sources/base.py` — `Deal` dostaje opcjonalne `ean, sku, mpn, brand_hint, attributes_hint` (backward compat).

### Dashboard

- `dashboard.py` — nowe routes: `GET /products`, `GET /products/{uuid}`, `GET /api/products`, `GET /api/products/{uuid}`, `GET /api/products/{uuid}/offers`, `GET /api/products/{uuid}/price-history`, `GET /review`, `POST /review/{id}/action`, `POST /products/{uuid}/merge`, `POST /products/{uuid}/split`, `POST /match_decisions/{id}/undo`.
- Nowe templaty: `products_list.html`, `product_detail.html` (timeline + wykres + active offers table + price history), `review_queue.html`.
- Istniejące templaty deals: link "Zobacz produkt" gdzie `product_id` znane.
- Nawigacja: nowa zakładka "Produkty".

### Joby

- `scripts/migrate_add_products_schema.py` — jednorazowa migracja.
- `scripts/backfill_products.py` — jednorazowy backfill, wznawialny.
- `scripts/eval_matching.py` — liczenie metryk na golden set.
- `scripts/fetch_fx_rates.py` — cron codziennie (NBP).
- `scripts/reindex_match_candidates.py` — cron nightly (faza G).

### Telegram

- `notifiers/telegram.py` — w `send_alert` i `send_price_drop_alert` dodać przycisk "Produkt" z deeplinkiem.
- Digest `--digest` — po cutoverze grupuje price drops per produkt.

### Feedback bot

- Nowa komenda `/product <uuid>`.
- `/watch <deal_id>` pracuje wewnętrznie na `product_id` gdzie dostępne; fallback na deal_id.
- Callback_data bez zmian (klucz: deal_id).

---

## 8. Testy i walidacja

### Unit

- `test_normalizer.py` — lowercase, diakrytyki, stopwords, separatory, normalizacja rozmiaru ("58cm" ≡ "58" ≡ "r.58").
- `test_extractor.py` — per źródło na fixtureach HTML/JSON: brand/model/EAN/SKU/attributes, edge cases.
- `test_matcher_l1.py` — twarde identyfikatory, idempotencja.
- `test_matcher_l2.py` — required_match_attrs (różny rozmiar → no merge), token_set_ratio progi, null-vs-known (blokuje).
- `test_matcher_negative_evidence.py` — "sticky no".
- `test_ceneo_group.py` — ceneo_group_id jako L2 + required_match_attrs konieczne.
- `test_fx_nbp.py` — NBP client, cache, fallback, konwersja.

### Integration

- `test_ingest_pipeline_products.py` — full flow: mock source → offer → match → product → deal event; idempotencja.
- `test_review_flow.py` — L3 → review → manual approve → alias utworzony → ponowny fetch trafia L1.
- `test_merge_split_undo.py` — merge → split → undo w 7 dni.
- `test_dashboard_products.py` — endpointy listy/detail/API; paginacja; filtry; Playwright E2E.
- `test_fx_alert_semantics.py` — price drop alert NIE odpala z samego ruchu kursu gdy oryginalna waluta nie zmieniła ceny.

### Migration tests

- `test_migration_schema.py` — na kopii real DB: idempotencja migracji, counts, brak dataloss.
- `test_backfill_products.py` — idempotencja backfillu, checkpoint recovery.

### Jakość matchowania

- Golden set ~200 par (same/different) per kategoria, `tests/fixtures/matching/golden/*.yaml`.
- Metryki skryptem `scripts/eval_matching.py` — precision, recall, F1, per warstwa.
- **Gates:**
  - L1 precision = 1.0 (hard).
  - L2 precision ≥ 0.98, recall ≥ 0.70.
  - L3 (review-only): mierzymy `human_accept_rate` po fazie E.
- Metryka operacyjna w `/health`: `manual_review_rate` (target steady-state < 20%; > 30% → tuning extractora).
- Alert tygodniowy: `false_merge_rate > 0.5%` → blokada cutoveru / rollback.
- Canary: cron co tydzień sample 20 auto-L2 do `match_reviews.status=audit_sample`.

### Dashboard sanity

- Produkt z N ofertami: min/max/mediana zgodne z PricePoint.
- Dezaktywacja oferty (`is_active=0`) nie psuje price history produktu.
- Cross-source timeline renderuje się przy brakach w jednym źródle.

---

## 9. Ryzyka i decyzje

### Ryzyka techniczne

- **Niskie pokrycie EAN/SKU** w polskich sklepach (Pepper prawie zero, Ceneo ma `ceneo_group_id` — gold, x-kom zmienne). L2 nosi większość ciężaru → wyższy `manual_review_rate`.
- **Cloudflare na x-kom** — store YAML istnieje, live scraping bywa blokowany. Produkt się utworzy, ale bez świeżych ofert.
- **Migracje SQLite ALTER** — preferujemy `ADD COLUMN` pojedynczo; cięższe zmiany: CREATE new → INSERT SELECT → DROP old → RENAME.
- **NBP API downtime** — cache + fallback na ostatni znany kurs, log ostrzeżenia.
- **Regex w profile YAML** (score_rules) i extractor — nie wchodzą sobie w drogę (extractor działa na raw_title przed scoringiem).

### Ryzyka produktowe

- **False merge psuje zaufanie do alertów** → rygor progów + required_match_attrs + canary.
- **FX-driven false price drops** → próg alertu liczony na price_original gdy waluta stała.
- **Watchlista użytkownika** — migracja musi zachować subskrypcje (fallback deal_id).
- **"Explosion of products"** — jeśli extractor słaby, każda oferta → nowy produkt → dashboard zaśmiecony. Mitigation: metryka `products_with_only_one_offer_after_30d` + manual merge.

### Decyzje podjęte (podczas brainstormingu)

| # | Decyzja |
|---|---|
| 1 | `required_match_attrs`: bikes: `{size, frame_color, year}`; nas_hdd: `{capacity_tb, form_factor}`. Inne profile: ustalane per profil przy implementacji. |
| 2 | `ceneo_group_id` jako sygnał L2 (nie L1), wymaga zgodności `required_match_attrs`. |
| 3 | Warianty cenowe na jednej stronie → N Offerów, suffix `#size=54` w `source_native_id`. |
| 4 | Waluty: konwersja do PLN z NBP już w MVP; price_original + fx_rate_used w PricePoint; próg alertu na price_original gdy waluta stała. |
| 5 | Cross-profile matching zablokowany, twarda bariera category. |
| 6 | Product.id = UUID, bez slugów. URL: `/products/{uuid}`. |
| 7 | Priority review queue = `score + (temp/20 jeśli Pepper) + (5 jeśli w budżecie)`. |
| 8 | MVP bez encji Family, tylko pole `attributes.family_key` (string). |
| 9 | Soft-delete Product po 180 dniach bez aktywnej oferty, flaga `archived=1`. |
| 10 | `offer_payload_history` jako osobna tabela, N=10 snapshotów FIFO per offer. |

### Decyzje do podjęcia przy implementacji (nie-blokery)

- `required_match_attrs` dla pozostałych profili (innych niż bikes i nas_hdd) — ustalić listę aktualnych profili i per-profil zdefiniować.
- Częstotliwość fetch NBP — proponowane raz dziennie o 06:00 (przed pierwszym cronem deal-huntera).
- Rozmiar FIFO dla OfferPayloadHistory — obecnie N=10; gdyby DB puchnąć, zmniejszyć do N=5.

---

## Rekomendowana kolejność wdrożenia (8 kroków)

1. **Schema + dual-write Offer + payload history** (Faza A) — tabele + migracja + zapis równoległy.
2. **Extractor + FX NBP + sekcja `identifiers:` w stores YAML** (Faza B) — ekstrakcja + konwersja walut + raport pokrycia.
3. **Pipeline L1 tylko** — auto-match po twardych identyfikatorach; brak matchu → nowy Product; backfill konserwatywny.
4. **Golden set + metryki + pipeline L2 z required_match_attrs** (Faza C cz. 2) — gate precision ≥ 0.98 przed włączeniem L2.
5. **Dashboard `/products` read-only** (Faza D) — równolegle do `/deals`, cross-source timeline.
6. **Manual review queue + undo** (Faza E) — L3 akcjonowalne, audit log, negative evidence.
7. **Cutover: Telegram + bot + watchlista produktowa** (Faza F) — `/products` default, canary audit OK.
8. **Background merge sweep** (Faza G, post-MVP) — nightly z limitami bezpieczeństwa.
