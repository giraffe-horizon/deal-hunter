# CLAUDE.md — Instrukcje dla Claude Code

## Projekt

**Deal Hunter** — uniwersalny, multi-source monitor okazji. Skanuje różne źródła (Pepper.pl, Ceneo.pl, Proshop.pl, dowolne strony via generic web scraper), ocenia oferty scoring engine'em z reguł YAML (z obsługą regex), śledzi zmiany cen, i wysyła alerty na Telegram + Notion.

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
sources/web.py          Generic web scraper (konfigurowalny CSS selectors z YAML)
filters/base.py         Bazowy scoring engine (score_rules, penalties, budget, temperature, regex)
filters/bike_filter.py  Rozszerzony scorer dla rowerów (rozmiary, kolory, opony, race keywords)
notifiers/telegram.py   Telegram Bot API z retry + rate limiting
notifiers/notion.py     Notion API (kategorie z profilu, opcjonalne per profil)
utils/validation.py     Walidacja profili YAML (typy, wymagane pola, sanity checks)
profiles/*.yaml         Profile produktów (gitignored poza example.yaml)
profiles/example.yaml   Przykładowy profil z opisem WSZYSTKICH opcji
docs/creating-profiles.md  Dokumentacja tworzenia profili
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

**Regex w score_rules/penalties/excluded_words/required_any:**
Keyword zaczynający się od `r/` i kończący na `/` jest traktowany jako regex (re.IGNORECASE).
Przykład: `"r/\\b(xl|58|59)\\b/": 10` — matchuje całe słowa xl, 58, 59.

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
- `currency` — waluta (domyślnie "PLN")
- `telegram` — `{topic_id, max_alerts}`
- `notion` — `{database_id, categories}` lub `null` (categories mapują nazwy kategorii na listy keywords)

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
python deal_hunter.py --profile bikes --validate  # walidacja profilu bez uruchamiania
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

**Alternatywnie:** użyj generic web scraper (`sources/web.py`) — nie wymaga kodu, konfiguracja CSS selectors w YAML:
```yaml
sources:
  web:
    sites:
      - url: "https://example.com/deals"
        base_url: "https://example.com"
        selectors:
          container: "div.product"
          title: "h2.name"
          price: "span.price"
          link: "a@href"        # @attr syntax — wyciąga atrybut HTML
          image: "img@src"
```

## Dodawanie nowego profilu

**WAŻNE:** Profile użytkownika NIE są w repo (gitignored). Tylko `profiles/example.yaml` jest commitowany.

1. Stwórz `profiles/nazwa.yaml` — wzoruj się na `profiles/example.yaml`
2. Szczegółowa dokumentacja: `docs/creating-profiles.md`
3. Jeśli potrzebny custom filtr → stwórz w `filters/`, zarejestruj w `FILTER_REGISTRY`, ustaw `custom_filter` w YAML

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

## Śledzenie cen (Price Tracking)

Deal Hunter automatycznie śledzi ceny znanych ofert. Stan zapisywany w `state/<profil>_state.json` pod kluczem `"prices"`.
- Jeśli oferta pojawi się ponownie z niższą ceną (spadek >10% lub >50 PLN) → dodatkowy plus w alercie
- Wzrost ceny → logowany, ale nie dodaje minus
- Nie wymaga konfiguracji — działa out of the box

## Walidacja profili

`utils/validation.py` → `validate_profile(profile) -> list[str]`

Sprawdza: wymagane pola, typy danych, sanity (budget.min < budget.max, score_threshold < score_threshold_alert).

CLI: `python deal_hunter.py --profile bikes --validate`

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
