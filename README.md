# Deal Hunter 🔍

Uniwersalny, multi-source monitor okazji. Definiujesz profil produktu w YAML — Deal Hunter skanuje źródła, ocenia oferty scoring engine'em, i wysyła alerty na Telegram + opcjonalnie Notion.

## Architektura

```
deal-hunter/
├── deal_hunter.py              Główny orchestrator (CLI)
├── sources/                    Pluginy źródeł (każde źródło = osobna klasa)
│   ├── base.py                 Klasa bazowa Source + dataclass Deal
│   ├── pepper.py               Pepper.pl — scraper Vue3 + HTML fallback
│   ├── ceneo.py                Ceneo.pl — porównywarka cen
│   └── proshop.py              Proshop.pl — scraper sklepowy
├── filters/                    Scoring engines
│   ├── base.py                 Bazowy scorer (ładuje reguły z YAML)
│   └── bike_filter.py          Rozszerzony scorer: rozmiary, kolory, opony
├── notifiers/                  Backendy powiadomień
│   ├── telegram.py             Telegram Bot API (retry + rate limiting)
│   └── notion.py               Notion API (opcjonalne per profil)
├── profiles/                   Profile produktów (YAML)
│   ├── bikes.yaml              🚲 Rowery endurance/gravel (Pepper)
│   └── nas_hdd.yaml            💾 Dyski HDD 12TB NAS (Pepper + Ceneo + Proshop)
├── state/                      Persistent state per profil (JSON, TTL 14 dni)
├── .env                        Tokeny i klucze (nie commitowane)
├── .env.example                Szablon zmiennych środowiskowych
├── requirements.txt            Zależności Pythona
└── LICENSE                     MIT
```

## Szybki start

```bash
# Klonuj
git clone https://github.com/giraffe-horizon/deal-hunter.git
cd deal-hunter

# Środowisko
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Konfiguracja
cp .env.example .env
# Edytuj .env — wpisz tokeny Telegram i ścieżkę do klucza Notion
```

## Użycie

```bash
# Uruchom profil
python deal_hunter.py --profile bikes
python deal_hunter.py --profile nas_hdd

# Tryb weryfikacji — pokazuje WSZYSTKIE oferty z scoring, bez zapisywania stanu
python deal_hunter.py --profile bikes --verify

# Uruchom wszystkie profile naraz
python deal_hunter.py --all

# Lista dostępnych profili
python deal_hunter.py --list
```

## Profile

| Profil | Emoji | Źródła | Budżet | Opis |
|--------|-------|--------|--------|------|
| `bikes` | 🚲 | Pepper | 10 000–15 000 PLN | Rowery endurance/gravel, carbon, Di2/AXS, rozmiar XL/58+ |
| `nas_hdd` | 💾 | Pepper, Ceneo, Proshop | 400–900 PLN | Dyski HDD 12TB NAS-grade (IronWolf, Exos, Ultrastar) |

## Tworzenie nowego profilu

Stwórz `profiles/nazwa.yaml`:

```yaml
name: nazwa
emoji: "🎯"

# Źródła do skanowania
sources:
  pepper:
    urls:
      - "https://www.pepper.pl/search?q=twoje+zapytanie"
  ceneo:
    queries:
      - "twoje zapytanie"
  proshop:
    queries:
      - "twoje zapytanie"

# Zakres cenowy (PLN)
budget:
  min: 100
  max: 500

# Słowa kluczowe → punkty (pozytywne)
score_rules:
  keyword1: 40
  keyword2: 25

# Kary (negatywne)
penalties:
  bad_keyword: -30

# Min. jedno z tych słów musi wystąpić (opcjonalne)
required_any:
  - "wymagane_slowo"

# Auto-odrzuć jeśli wystąpi (opcjonalne)
excluded_words:
  - "odrzuć_to"

# Progi scoring
score_threshold: 50        # min. score dla alertu
score_threshold_alert: 80  # score dla "gorącej perełki"

# Custom filtr (opcjonalne) — nazwa klasy z filters/
# custom_filter: bike_filter.BikeFilter

# Powiadomienia
telegram:
  topic_id: 31
  max_alerts: 5

# Notion (null = brak)
notion: null
# notion:
#   database_id: "your-notion-db-id"
```

## Źródła

| Źródło | Typ | Konfiguracja w profilu |
|--------|-----|----------------------|
| **Pepper.pl** | Agregator okazji | `urls` — lista URLi do skanowania |
| **Ceneo.pl** | Porównywarka cen | `queries` — lista zapytań wyszukiwania |
| **Proshop.pl** | Sklep online | `queries` — lista zapytań wyszukiwania |

Każde źródło ma wbudowany rate limiting (min 2s między requestami), retry z exponential backoff, i graceful degradation (jedno źródło padnie → reszta działa).

### Dodawanie nowego źródła

1. Stwórz `sources/nazwa.py` — klasa dziedzicząca po `Source`
2. Zaimplementuj `fetch_deals(config) → list[Deal]`
3. Zarejestruj w `sources/__init__.py`

## Scoring

Bazowy scoring engine (`filters/base.py`):
1. **Excluded words** → hard reject
2. **Required any** → min. 1 musi matchować, inaczej reject
3. **Score rules** → keyword w title+description = +punkty
4. **Penalties** → keyword = -punkty
5. **Budget** → w budżecie +5, za tanio -20, za drogo -30
6. **Temperatura** (Pepper) → gorąca +10, ciepła +5, zimna -10

Custom filtry (np. `BikeFilter`) rozszerzają bazowy scorer o dodatkową logikę (rozmiary per marka, kolory, szerokość opon, race keywords).

### Tiery alertów

| Score | Tier | Emoji |
|-------|------|-------|
| ≥ `score_threshold_alert` | GORĄCA PEREŁKA | 🔥🔥🔥 |
| ≥ `score_threshold` | OKAZJA | 🔥 |
| ≥ 20 | MOŻE | 🤔 |
| < 20 | NIE PASUJE | ❌ |

## Cron

```bash
# Rowery — co 30 min
*/30 * * * * cd ~/Projects/deal-hunter && venv/bin/python deal_hunter.py --profile bikes >> deal_hunter.log 2>&1

# HDD NAS — co 30 min
*/30 * * * * cd ~/Projects/deal-hunter && venv/bin/python deal_hunter.py --profile nas_hdd >> deal_hunter.log 2>&1

# Albo wszystko naraz
*/30 * * * * cd ~/Projects/deal-hunter && venv/bin/python deal_hunter.py --all >> deal_hunter.log 2>&1
```

## Zmienne środowiskowe

| Zmienna | Opis | Wymagana |
|---------|------|----------|
| `TELEGRAM_BOT_TOKEN` | Token bota Telegram | ✅ |
| `TELEGRAM_CHAT_ID` | ID czatu/grupy Telegram | ✅ |
| `NOTION_API_KEY_PATH` | Ścieżka do pliku z kluczem Notion API | ❌ (tylko jeśli profil używa Notion) |

## Licencja

MIT — patrz [LICENSE](LICENSE).
