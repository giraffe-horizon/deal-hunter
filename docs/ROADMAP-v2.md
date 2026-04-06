# Deal Hunter — Roadmap v2.0

**Data:** 2026-04-06
**Status:** Zatwierdzony przez Łukasza

---

## Faza A — Jakość alertów

### A.1 Scoring Tuner
**Cel:** Live podgląd jak zmiana reguł wpływa na istniejące oferty w bazie. Zero restartowania, zero ręcznego `--verify`.

**Implementacja:**
- Nowy widok w dashboardzie: `/tuner/<profile>`
- Edytor reguł (score_rules, penalties, progi) — zmiany in-memory, nie zapisywane
- Live tabela: oferty z bazy posortowane po nowym score, diff vs. obecny score (zielony/czerwony)
- Przycisk "Zapisz profil" — nadpisuje YAML na dysku
- Przycisk "Test run (dry)" — odpala `--profile <name> --verify` w tle, wynik w UI

**Effort:** L (~10h)
**Zależności:** Dashboard (✅ Done)

---

### A.2 Deduplikacja cross-source
**Cel:** Ten sam produkt z Pepper + Rowertour + Sprint = 1 alert, nie 3.

**Implementacja:**
- Fuzzy match po znormalizowanym tytule (lowercase, strip brand suffixes) + zakres cenowy ±5%
- Merge: najlepsza oferta (najniższa cena) jako główna, pozostałe linki jako "też dostępne w:"
- Format alertu: `[🔗 Pepper] [🔗 Rowertour] [🔗 Sprint]` — wszystkie źródła w jednym
- Config per profil: `dedup: {enabled: true, price_tolerance: 0.05, title_similarity: 0.85}`
- Metryka w health.json: `dedup_merged: N` per run

**Effort:** M (~6h)
**Zależności:** SQLite (✅ Done)

---

### A.3 Quiet Hours
**Cel:** Brak alertów w nocy. Konfigurowalny per profil lub globalnie.

**Implementacja:**
- Config w `.env`: `QUIET_HOURS_START=23:00`, `QUIET_HOURS_END=07:00`, `TZ=Europe/Warsaw`
- Override per profil YAML: `telegram: {quiet_hours: {start: "22:00", end: "08:00"}}`
- Alerty wstrzymane → kolejkowane w SQLite (`alerts_queue` table)
- O końcu quiet hours: flush kolejki (max 5 alertów, reszta w digest)
- `--watchdog` i `--digest` ignorują quiet hours

**Effort:** S (~4h)
**Zależności:** SQLite (✅ Done)

---

## Faza B — Nowe źródła

### B.1 x-kom / Morele
**Cel:** Pokrycie największych polskich sklepów elektronicznych. Rowery, komponenty, elektronika.

**Implementacja:**
- YAML store: `stores/xkom.yaml` — CSS selectors z x-kom.pl
- YAML store: `stores/morele.yaml` — CSS selectors z morele.net
- Testowanie na profilu `bikes` (komponenty, akcesoria) i `nas_hdd`
- Dodanie do przykładowego profilu w `examples/`

**Effort:** S (~3h)
**Zależności:** YAML source engine (✅ Done)

---

### B.2 Allegro Okazje (RSS)
**Cel:** Monitoring Allegro bez OAuth, tylko publiczne RSS dla wybranych kategorii/fraz.

**Implementacja:**
- Nowy source: `sources/rss.py` — generyczny RSS/Atom parser
- Auto-wykrywanie feedów Allegro: `https://allegro.pl/rss/listing?string=<query>&...`
- Config w profilu YAML:
  ```yaml
  sources:
    rss:
      feeds:
        - url: "https://allegro.pl/rss/listing?string=rower+endurance&price_from=8000&price_to=15000"
        - url: "https://allegro.pl/rss/listing?string=canyon+endurace"
  ```
- Parsowanie: title, price (z description regex), link, published_at
- Rejestracja w `SOURCE_REGISTRY`

**Effort:** M (~5h)
**Zależności:** Brak

---

## Faza C — Dashboard UX

### C.1 Watchlist z Price Alertem
**Cel:** Śledzenie konkretnych ofert z własnym progiem cenowym. "Powiadom gdy Canyon Endurace spadnie poniżej 9000 PLN".

**Implementacja:**
- Przycisk "Obserwuj" na stronie szczegółów oferty → modal z polem "alert gdy cena < X PLN"
- Nowa tabela SQLite: `watchlist (deal_id, target_price, created_at, notified_at)`
- Per-run check: jeśli `current_price <= target_price` → Telegram alert z formatem:
  ```
  🎯 CEL CENOWY OSIĄGNIĘTY
  Canyon Endurace CF 7
  Twój próg: 9 000 zł | Obecna cena: 8 499 zł
  [🔗 Otwórz]
  ```
- Widok `/watchlist` w dashboardzie: lista, edycja progów, usuwanie
- Komenda `/watchlist` w feedback bocie

**Effort:** M (~6h)
**Zależności:** SQLite (✅ Done), Feedback bot (✅ Done)

---

### C.2 Porównywarka
**Cel:** Side-by-side porównanie 2-5 ofert — spec, cena, score, historia cenowa.

**Implementacja:**
- Checkbox przy każdej ofercie na liście → floating bar "Porównaj (N)" → `/compare?ids=...`
- Widok `/compare` — tabela: wiersze = atrybuty (cena, score, źródło, data, opis), kolumny = oferty
- Mini sparkline price history per oferta (Chart.js inline)
- Highlight: najlepsza cena (zielona), najwyższy score (złoty)
- Share link: `/compare?ids=id1,id2,id3` (bookmarkowalny)

**Effort:** M (~6h)
**Zależności:** SQLite (✅ Done), Dashboard (✅ Done)

---

### C.4 Zarządzanie profilami
**Cel:** Pełne CRUD profili przez przeglądarkę. Zero SSH, zero edytora plików.

**Implementacja:**

#### Przeglądanie
- Widok `/profiles` — lista profili z metadanymi: nazwa, emoji, liczba źródeł, progi, ostatni run
- Podgląd YAML — raw + syntax highlight (highlight.js przez CDN)
- Status per profil: ostatni run, liczba dealów, liczba alertów, błędy

#### Edycja
- Dwa tryby:
  - **Formularz** — sekcje: Podstawowe (nazwa, emoji, budżet), Źródła (dodaj/usuń URL per source), Scoring (tabela reguł z +/- punktami), Progi
  - **Raw YAML editor** — CodeMirror przez CDN, walidacja on-save
- Zapis → `PUT /api/profiles/<name>` → zapis do `profiles/<name>.yaml`
- Auto-walidacja przez `utils/validation.py` przed zapisem, błędy wyświetlane inline

#### Tworzenie
- Wizard `/profiles/new` — 4 kroki:
  1. Podstawowe (nazwa, emoji, budżet min/max)
  2. Źródła (checkboxy dostępnych stores + custom URLs)
  3. Scoring (suggested keywords z autouzupełnianiem, progi)
  4. Test run — podgląd pierwszych wyników bez zapisu stanu
- Alternatywnie: "Importuj YAML" — wklej/wgraj gotowy plik

#### Usuwanie / Disable
- Przycisk "Wyłącz" → `enabled: false` w YAML → cron pomija profil
- Przycisk "Usuń" → modal potwierdzenia → usuwa plik + czyści state

#### Ręczny trigger
- Przycisk "▶ Uruchom teraz" per profil
- Backend: `POST /api/profiles/<name>/run` → subprocess `deal_hunter.py --profile <name>`
- Live log w UI przez SSE (Server-Sent Events) lub polling co 2s
- Po zakończeniu: odświeżenie statystyk profilu

#### API
```
GET    /api/profiles              # lista profili
GET    /api/profiles/<name>       # szczegóły + YAML
POST   /api/profiles              # nowy profil
PUT    /api/profiles/<name>       # aktualizacja
DELETE /api/profiles/<name>       # usunięcie
PATCH  /api/profiles/<name>/toggle # enable/disable
POST   /api/profiles/<name>/run   # trigger run
GET    /api/profiles/<name>/run/status  # SSE stream logu
```

**Effort:** XL (~20h)
**Zależności:** Dashboard (✅ Done), validation.py (✅ Done)

---

## Podsumowanie

| Faza | Feature | Effort | Priorytet | Status |
|------|---------|--------|-----------|--------|
| A.1 | Scoring Tuner | L (10h) | Wysoki | |
| A.2 | Deduplikacja cross-source | M (6h) | Wysoki | |
| A.3 | Quiet Hours | S (4h) | Średni | ✅ Done |
| B.1 | x-kom / Morele stores | S (3h) | Średni | ✅ Done |
| B.2 | Allegro RSS source | M (5h) | Średni | ✅ Done |
| C.1 | Watchlist z price alertem | M (6h) | Wysoki | |
| C.2 | Porównywarka | M (6h) | Niski | |
| C.4 | Zarządzanie profilami (full CRUD) | XL (20h) | Wysoki | |

**Szacowany łączny effort:** ~60h
**Rekomendowana kolejność:** A.3 → A.2 → C.1 → B.1 → B.2 → C.4 → A.1 → C.2
