# Deal Hunter — Roadmap v1.0

**Data:** 2026-04-04
**Status:** Do zatwierdzenia

---

## Faza 0 — Cleanup (Notion removal)

### 0.1 Usunięcie Notion integrations
**Cel:** Uprościć stack, usunąć zewnętrzną zależność. Notion zostanie zastąpiony lokalnym SQLite + dashboardem w Fazie 3.

**Zakres:**
- Usunąć `notifiers/notion.py`
- Usunąć import i rejestrację NotionNotifier z `notifiers/__init__.py`
- Usunąć sekcje `notion:` z profili: `bikes.yaml`, `nas_hdd.yaml`, `example.yaml`
- Usunąć `NOTION_API_KEY_PATH` z `.env.example` i `.env` (local)
- Wyczyścić `deal_hunter.py` — logika inicjalizacji Notion, wywołania notify
- Update `README.md` — usunąć wzmiankę o Notion z Features, Quick Start, Architecture
- Update `CLAUDE.md` — usunąć Notion z opisu architektury i konwencji
- Update `docs/creating-profiles.md` — usunąć sekcję `notion:` z template'u
- Usunąć testy związane z Notion (jeśli istnieją)

**Effort:** S (~2h)
**Zależności:** Brak
**Ryzyko:** Niskie — czysto subtraktywne, żadna nowa logika

---

## Faza 1 — Monitoring & DevOps

### 1.1 Health monitoring
**Cel:** Wiedzieć że cron działa. Wykrywać ciche awarie (jak ta z 20-31 marca).

**Implementacja:**
- Po każdym runie zapisywać `state/health.json`:
  ```json
  {
    "last_run": "2026-04-04T14:30:00",
    "status": "ok|partial|error",
    "profile_results": {
      "bikes": {"status": "ok", "deals_found": 224, "new_alerts": 0, "errors": []},
      "nas_hdd": {"status": "ok", "deals_found": 5, "new_alerts": 0, "errors": []}
    },
    "sources_health": {
      "pepper": {"status": "ok", "last_success": "...", "consecutive_failures": 0},
      "canyon": {"status": "ok", "last_success": "...", "consecutive_failures": 0}
    },
    "version": "1.1.0"
  }
  ```
- Nowy CLI flag: `--health` — wyświetla status ostatniego runu, czas od ostatniego runu, błędy
- Nowy CLI flag: `--watchdog` — sprawdza czy ostatni run był <2h temu, jeśli nie → Telegram alert
- Cron: dodać osobny wpis `0 */3 * * * deal_hunter.py --watchdog` (co 3h sprawdza)

**Effort:** S (~3h)
**Zależności:** Brak
**Ryzyko:** Niskie

### 1.2 CHANGELOG + semantic versioning
**Cel:** Śledzenie zmian, profesjonalne releases.

**Implementacja:**
- Dodać `CHANGELOG.md` z formatem [Keep a Changelog](https://keepachangelog.com/)
- Bump wersji w `deal_hunter.py` (`__version__`)
- GitHub Action: auto-generate release notes z conventional commits przy tagu `v*`
- Konwencja commitów: `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`

**Effort:** S (~1h)
**Zależności:** Brak
**Ryzyko:** Brak

### 1.3 Docker Compose
**Cel:** Powtarzalny deploy, zero dependency hell.

**Implementacja:**
- `Dockerfile`:
  - Base: `python:3.12-slim`
  - Install requirements.txt
  - Copy sources, filters, notifiers, utils, stores, deal_hunter.py
  - Entrypoint: cron daemon lub `deal_hunter.py`
- `docker-compose.yaml`:
  - Service `deal-hunter` z cron wewnątrz (supercronic albo system cron)
  - Volumes: `./profiles:/app/profiles`, `./state:/app/state`, `./.env:/app/.env`
  - Optional: service `watchdog` z `--watchdog` co 3h
- `.dockerignore`: venv, .git, __pycache__, tests, docs
- README update z sekcją Docker deployment

**Effort:** M (~4h)
**Zależności:** Brak
**Ryzyko:** Niskie — standardowy Docker setup

---

## Faza 2 — Lepsze alerty

### 2.1 Konfigurowalny price drop alert
**Cel:** Proaktywne powiadomienia o spadkach cen na znanych ofertach.

**Implementacja:**
- Nowa sekcja w profilu YAML:
  ```yaml
  price_tracking:
    enabled: true
    min_drop_percent: 15    # minimum % spadku żeby powiadomić
    min_drop_amount: 200    # minimum PLN spadku (oba warunki OR)
    track_increases: false  # czy powiadamiać o wzrostach
  ```
- Rozbudowa `state/<profile>_state.json` → sekcja `prices`:
  ```json
  {
    "prices": {
      "deal_id": {
        "history": [
          {"price": 12999, "date": "2026-04-01"},
          {"price": 10499, "date": "2026-04-04"}
        ],
        "lowest": 10499,
        "highest": 12999
      }
    }
  }
  ```
- Telegram alert format:
  ```
  📉 SPADEK CENY
  Canyon Endurace CF 8 Di2
  12 999 zł → 10 499 zł (-19%, -2 500 zł)
  Najniższa cena w historii! 🔥
  ```
- Osobna sekcja w Telegram summary: "Price drops this run: X"

**Effort:** M (~6h)
**Zależności:** Brak (price tracking już częściowo istnieje)
**Ryzyko:** Niskie

### 2.2 Verbose scoring breakdown
**Cel:** Debugowanie profili — widzieć DLACZEGO oferta dostała tyle punktów.

**Implementacja:**
- Nowy flag: `--verify --verbose` (lub `--explain`)
- Output per oferta:
  ```
  ┌─ Canyon Endurace CF 8 Di2 — SCORE: 185 ✅
  │  +50  endurance (title match)
  │  +45  endurace (title match)
  │  +40  di2 (title match)
  │  +35  carbon (title match)
  │  +15  disc (title match)
  │  +10  size XL (regex match)
  │  -10  no brand size match
  │  Budget: IN RANGE (12 999 zł) → +5
  │  Temperature: 145° → +10
  └─ Final: 185 (threshold: 120) → ALERT ✅
  ```
- Zależność: `rich` library (optional, fallback to plain text)
- Refactor: `ScoreResult` rozszerzyć o `breakdown: list[ScoreEntry]`

**Effort:** S (~4h)
**Zależności:** Refactor ScoreResult
**Ryzyko:** Niskie

### 2.3 Telegram inline keyboard
**Cel:** Interakcja z alertami bezpośrednio z Telegrama.

**Implementacja:**
- Przy każdym alercie Telegram — inline keyboard:
  ```
  [🔗 Otwórz] [⭐ Obserwuj] [👎 Nie interesuje]
  ```
- Mini webhook (FastAPI, <100 LOC):
  - Endpoint: `/telegram/callback`
  - "Otwórz" → otwiera link (Telegram robi to natywnie z URL button)
  - "Obserwuj" → dodaje deal do `state/watchlist.json` (price tracking z niższym progiem)
  - "Nie interesuje" → dodaje do `state/feedback.json` (blacklist title/source combo)
- Deploy: osobny mały serwis w Docker Compose
- Long-term: feedback wpływa na scoring (negative feedback na brand/source = penalty)
- Wymaga ustawienia Telegram webhook URL (ngrok/Tailscale/publiczny IP)

**Effort:** L (~8h)
**Zależności:** Docker Compose (1.3), publiczny endpoint
**Ryzyko:** Średnie — wymaga publicznego endpointu dla webhook

---

## Faza 3 — Wizualizacja & Persistence

### 3.1 SQLite persistence (zastępuje Notion)
**Cel:** Lokalna baza zamiast Notion. Fundament dla dashboardu i chart'ów.

**Implementacja:**
- Nowy moduł: `storage/sqlite.py`
- Schema:
  ```sql
  CREATE TABLE deals (
    id TEXT PRIMARY KEY,          -- "{source}:{native_id}"
    title TEXT NOT NULL,
    price INTEGER,
    link TEXT,
    source TEXT,
    description TEXT,
    image_url TEXT,
    profile TEXT,                  -- "bikes", "nas_hdd"
    score INTEGER,
    category TEXT,                 -- z profilu (szosowy, gravel, etc.)
    first_seen DATETIME,
    last_seen DATETIME,
    status TEXT DEFAULT 'active'   -- active|watching|rejected
  );

  CREATE TABLE price_history (
    deal_id TEXT REFERENCES deals(id),
    price INTEGER,
    recorded_at DATETIME,
    PRIMARY KEY (deal_id, recorded_at)
  );

  CREATE TABLE feedback (
    deal_id TEXT REFERENCES deals(id),
    action TEXT,                   -- "watch"|"skip"|"open"
    created_at DATETIME
  );
  ```
- Migracja: dane z `state/*.json` → SQLite (jednorazowy skrypt)
- Profil YAML: opcjonalny `storage: sqlite` (default, jedyna opcja po usunięciu Notion)

**Effort:** M (~6h)
**Zależności:** Faza 0 (Notion usunięty)
**Ryzyko:** Niskie

### 3.2 Price history charts
**Cel:** Wizualizacja trendów cenowych.

**Implementacja:**
- Generowanie wykresów z `price_history` table
- CLI: `--price-chart <deal_id>` lub `--price-chart --profile bikes --top 5`
- Output: PNG → wysyłka do Telegrama
- Library: matplotlib (statyczne) lub plotly (jeśli dashboard)
- Tygodniowy digest: top 5 spadków cen za ostatni tydzień → Telegram summary z wykresami

**Effort:** M (~5h)
**Zależności:** 3.1 (SQLite)
**Ryzyko:** Niskie

### 3.3 Dashboard webowy
**Cel:** Przeglądanie ofert, porównywanie, trendy — zastępuje Notion UI.

**Implementacja:**
- Stack: FastAPI + Jinja2 + HTMX (zero JS frameworków, server-side rendering)
- Widoki:
  - **Oferty** — lista z filtrami (source, score range, budżet, kategoria, status)
  - **Szczegóły oferty** — scoring breakdown, price history chart, feedback buttons
  - **Price trends** — wykresy per profil, top spadki
  - **Health** — status source'ów, ostatni run, error log
  - **Scoring tuner** — podgląd jak zmiana reguł wpłynie na istniejące oferty (nice-to-have)
- Auth: basic auth lub brak (local only, za Tailscale)
- Deploy: service w Docker Compose, port 8080
- Mobile-friendly: responsive CSS (Pico CSS albo similar minimal framework)

**Effort:** L (~16h)
**Zależności:** 3.1 (SQLite), 3.2 (charts), 2.2 (scoring breakdown)
**Ryzyko:** Średnie — największy feature, ale brak external dependencies

---

## Podsumowanie

| Faza | Feature | Effort | Status |
|------|---------|--------|--------|
| 0 | Notion removal | S (2h) | ✅ Done |
| 1.1 | Health monitoring | S (3h) | ✅ Done |
| 1.2 | CHANGELOG + semver | S (1h) | 🟡 Backlog |
| 1.3 | Docker Compose | M (4h) | ✅ Done |
| 2.1 | Price drop alerts | M (6h) | ✅ Done |
| 2.2 | Verbose scoring | S (4h) | ✅ Done |
| 2.3 | Telegram inline KB | L (8h) | ✅ Done |
| 3.1 | SQLite persistence | M (6h) | ✅ Done |
| 3.2 | Price charts | M (5h) | ✅ Done |
| 3.3 | Dashboard | L (16h) | ✅ Done |

**Roadmap v1.0 complete** (2026-04-06). Remaining: 1.2 CHANGELOG (nice-to-have).

**Uwagi po review rady nadzorczej (2026-04-04):**
- SQLite (3.1) przesunięty zaraz po Notion cleanup — fundament pod wszystko
- Dashboard (3.3) pozostaje, ale UI budowany w **Google Stitch** zamiast FastAPI+HTMX
- Systemd timer + OnFailure zamiast osobnego cron watchdoga
- Telegram feedback jako polling bot zamiast webhooka FastAPI
- Docker Compose dopiero gdy będzie więcej serwisów (3.3+)
- Chart.js przez CDN zamiast matplotlib PNG
- CHANGELOG przesunięty na koniec (nice-to-have)
