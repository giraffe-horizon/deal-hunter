# CLAUDE.md — Instrukcje dla Claude Code

## Projekt

**Deal Hunter** — uniwersalny, multi-source monitor okazji. Skanuje różne źródła (Pepper.pl, Ceneo.pl, Proshop.pl), ocenia oferty scoring engine'em z reguł YAML, i wysyła alerty na Telegram + Notion.

## Stack technologiczny

- **Python 3.12+** (venv w `./venv/`)
- **requests** — HTTP
- **beautifulsoup4** — scraping HTML
- **pyyaml** — profile produktów
- **python-dotenv** — zmienne środowiskowe z `.env`
- Brak frameworka webowego — to CLI tool na cronie

## Architektura

```
deal_hunter.py          Orchestrator: ładuje profil → źródła → scoring → notyfikacje
sources/base.py         Klasa bazowa Source + dataclass Deal (wspólny format)
sources/pepper.py       Scraper Pepper.pl (Vue3 JSON + HTML fallback)
sources/ceneo.py        Scraper Ceneo.pl (wyniki wyszukiwania)
sources/proshop.py      Scraper Proshop.pl (wyniki wyszukiwania)
filters/base.py         Bazowy scoring engine (score_rules, penalties, budget, temperature)
filters/bike_filter.py  Rozszerzony scorer dla rowerów (rozmiary, kolory, opony, race keywords)
notifiers/telegram.py   Telegram Bot API z retry + rate limiting
notifiers/notion.py     Notion API (opcjonalne per profil)
profiles/*.yaml         Profile produktów
state/*.json            Persistent state per profil (co już widziane, TTL 14 dni)
```

## Kluczowe wzorce

### Deal (dataclass)
Każde źródło zwraca listę `Deal` o tym samym formacie:
```python
@dataclass
class Deal:
    id: str           # "{source}:{native_id}" — unikalny cross-source
    title: str
    price: int        # PLN, 0 jeśli brak
    link: str
    source: str       # "pepper", "ceneo", "proshop"
    description: str
    temperature: int   # Pepper only, reszta 0
    image_url: str
    published_at: str  # ISO datetime lub ""
```

### Source plugin
```python
class Source(ABC):
    def fetch_deals(self, config: dict) -> list[Deal]:
        # config = to co jest pod kluczem źródła w profilu YAML
        pass
```
Źródła mają wbudowany rate limiting (`MIN_REQUEST_INTERVAL = 2s`), retry z backoff, i `_fetch_page()` helper.

### Scoring
`BaseFilter.score_deal(deal) → ScoreResult(score, plus, minus, rejected, reject_reason)`

Flow:
1. Excluded words → hard reject
2. Required any → reject jeśli żaden nie matchuje
3. Score rules → `+punkty` per keyword match w title+desc
4. Penalties → `-punkty` per keyword match
5. Budget → w budżecie +5, za tanio -20, za drogo -30
6. Temperatura (Pepper) → gorąca ≥100° +10, ciepła ≥50° +5, zimna <-10° -10

Custom filtry (np. `BikeFilter`) dziedziczą po `BaseFilter` i override'ują `score_deal()` z dodatkową logiką.

### Profil YAML
Każdy profil (`profiles/*.yaml`) definiuje:
- `name`, `emoji` — identyfikacja
- `sources` — dict z konfiguracją per źródło
- `budget` — `{min, max}`
- `score_rules` — `keyword: punkty`
- `penalties` — `keyword: kara`
- `required_any`, `excluded_words` — filtry (opcjonalne)
- `custom_filter` — nazwa klasy filtra np. `"bike_filter.BikeFilter"` (opcjonalne)
- `custom_data` — dowolne dane dla custom filtra (np. rozmiary per markę)
- `score_threshold`, `score_threshold_alert` — progi
- `telegram` — `{topic_id, max_alerts}`
- `notion` — `{database_id}` lub `null`

### Rejestracja pluginów
- Źródła: `sources/__init__.py` → `SOURCE_REGISTRY = {"pepper": PepperSource, ...}`
- Filtry: `filters/__init__.py` → `FILTER_REGISTRY = {"bike_filter.BikeFilter": BikeFilter, ...}`

## Jak uruchomić

```bash
source venv/bin/activate
python deal_hunter.py --profile bikes --verify   # test bez zapisu stanu
python deal_hunter.py --profile nas_hdd           # normalny run
python deal_hunter.py --all                        # wszystkie profile
python deal_hunter.py --list                       # lista profili
```

## Zmienne środowiskowe

Plik `.env` (nie commitowany):
```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
NOTION_API_KEY_PATH=~/.config/notion/api_key
```

## Dodawanie nowego źródła

1. Stwórz `sources/nowe_zrodlo.py`
2. Klasa dziedziczy po `Source`, implementuje `fetch_deals(config) -> list[Deal]`
3. Użyj `self._fetch_page(url)` i `self._rate_limit()` z klasy bazowej
4. Zarejestruj w `sources/__init__.py`: `SOURCE_REGISTRY["nowe_zrodlo"] = NoweZrodloSource`
5. Dodaj konfigurację źródła do profili YAML

## Dodawanie nowego profilu

1. Stwórz `profiles/nazwa.yaml` — wzoruj się na `nas_hdd.yaml` (prosty) lub `bikes.yaml` (z custom filtrem)
2. Jeśli potrzebny custom filtr → stwórz w `filters/`, zarejestruj w `FILTER_REGISTRY`, ustaw `custom_filter` w YAML

## Dodawanie custom filtra

1. Stwórz `filters/nowy_filter.py`
2. Klasa dziedziczy po `BaseFilter`, override `score_deal(deal) -> ScoreResult`
3. **Zawsze wywołuj** `result = super().score_deal(deal)` na początku — bazowy scorer obsługuje universalne reguły
4. Dodatkowe dane z `self.profile.get("custom_data", {})`
5. Zarejestruj w `filters/__init__.py`

## Konwencje kodu

- **Język komentarzy/docstringów:** angielski (kod) + polski (profile YAML, README, komunikaty Telegram)
- **Logging:** `logging` module, nie `print()` (wyjątek: `--verify` mode drukuje na stdout)
- **Error handling:** graceful degradation — jedno źródło padnie → reszta działa, jeden notify fail → reszta działa
- **Rate limiting:** każdy source ma min 2s między requestami, Telegram 1.5s + retry na 429
- **State:** per-profil JSON w `state/`, TTL 14 dni, cross-source deduplikacja po title+price
- **Secrets:** NIGDY w kodzie — `.env` + `python-dotenv`, `.gitignore` chroni `.env`

## Testy

Brak testów jednostkowych (TODO). Testowanie manualne:
```bash
# Weryfikacja scoringu — pokazuje wszystkie oferty z punktacją
python deal_hunter.py --profile bikes --verify
python deal_hunter.py --profile nas_hdd --verify
```

## Znane ograniczenia

- Ceneo i Proshop scrapują HTML — zmiana layoutu = trzeba zaktualizować parser
- Brak Allegro (wymaga API key + OAuth)
- Brak OLX, Morele, x-kom (do dodania)
- Pepper może blokować po wielu requestach — dlatego rate limiting
- Cross-source deduplikacja jest prosta (title+price) — może nie łapać wariantów tego samego produktu

## Git workflow

- Branch: `main` (jedyny)
- Remote: `origin` → `github.com/giraffe-horizon/deal-hunter`
- Commituj z sensownym message: `feat:`, `fix:`, `chore:`, `docs:`
- Push z tokenem jarvis-gh (skonfigurowany w remote URL)
