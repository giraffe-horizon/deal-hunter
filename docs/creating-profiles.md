# Tworzenie profili — Przewodnik

## Spis treści

1. [Wprowadzenie](#wprowadzenie)
2. [Szybki start](#szybki-start)
3. [Struktura pliku YAML](#struktura-pliku-yaml)
4. [Źródła danych](#źródła-danych)
5. [System scoringu](#system-scoringu)
6. [Custom filtry](#custom-filtry)
7. [Powiadomienia](#powiadomienia)
8. [Przykłady](#przykłady)
9. [FAQ i porady](#faq-i-porady)

---

## Wprowadzenie

Profil to plik YAML w katalogu `profiles/`, który definiuje **co szukasz** i **jak oceniać oferty**. Jeden profil = jeden typ produktu (np. rowery, dyski, słuchawki).

Jak to działa:
1. Deal Hunter ładuje profil
2. Skanuje zdefiniowane źródła (Pepper, Ceneo, Proshop)
3. Każda znaleziona oferta przechodzi przez scoring engine
4. Oferty powyżej progu → alert na Telegram (+ opcjonalnie Notion)
5. State zapisywany lokalnie → te same oferty nie alertują ponownie

Profile użytkownika **nie są commitowane do repo** (`.gitignore`). Wzoruj się na `profiles/example.yaml`.

## Szybki start

```bash
# Skopiuj template
cp profiles/example.yaml profiles/moj_profil.yaml

# Edytuj
nano profiles/moj_profil.yaml

# Przetestuj (--verify pokazuje scoring bez wysyłania alertów)
python deal_hunter.py --profile moj_profil --verify

# Uruchom normalnie
python deal_hunter.py --profile moj_profil
```

## Struktura pliku YAML

### Pola podstawowe

| Pole | Typ | Wymagane | Opis |
|------|-----|----------|------|
| `name` | string | ✅ | Nazwa profilu (używana w `--profile nazwa`) |
| `emoji` | string | ✅ | Emoji w alertach Telegram |
| `sources` | dict | ✅ | Konfiguracja źródeł (min. jedno) |
| `budget` | dict | ✅ | Zakres cenowy `{min, max}` w PLN |
| `score_rules` | dict | ✅ | Słowa kluczowe → punkty (pozytywne) |
| `penalties` | dict | ✅ | Słowa kluczowe → kary (ujemne) |
| `score_threshold` | int | ✅ | Min. score aby wysłać alert |
| `score_threshold_alert` | int | ✅ | Score dla "gorącej perełki" 🔥🔥🔥 |
| `telegram` | dict | ✅ | Konfiguracja Telegram |

### Pola opcjonalne

| Pole | Typ | Domyślnie | Opis |
|------|-----|-----------|------|
| `required_any` | list | `[]` | Min. jedno słowo musi matchować (hard reject) |
| `excluded_words` | list | `[]` | Którekolwiek słowo → hard reject |
| `custom_filter` | string | `null` | Nazwa klasy custom filtra |
| `custom_data` | dict | `{}` | Dowolne dane dla custom filtra |
| `notion` | dict/null | `null` | Konfiguracja Notion (`null` = wyłączone) |

### Budżet

```yaml
budget:
  min: 400   # poniżej → kara -20 pkt
  max: 900   # powyżej → kara -30 pkt
             # w zakresie → bonus +5 pkt
```

Budżet wpływa na scoring:
- **W zakresie**: +5 punktów
- **Za tanio** (poniżej min): -20 punktów (prawdopodobnie inny/gorszy produkt)
- **Za drogo** (powyżej max): -30 punktów

---

## Źródła danych

Dostępne trzy źródła. Możesz użyć jednego, dwóch lub wszystkich trzech.

### Pepper.pl

Agregator okazji i promocji. Użytkownicy wrzucają deale, społeczność głosuje (temperatura).

```yaml
sources:
  pepper:
    urls:
      - "https://www.pepper.pl/search?q=twoje+zapytanie"
      - "https://www.pepper.pl/grupa/nazwa-kategorii"
```

**Konfiguracja:** Lista URLi — mogą to być strony wyszukiwania lub kategorii Pepper.

**Zalety:**
- Temperatura oferty (społeczny dowód jakości)
- Szerokie pokrycie — różne sklepy w jednym miejscu

**Porady:**
- Dodaj kilka wariantów zapytań (synonimy, nazwy modeli)
- Możesz dodać kolejne strony wyników: `?page=2`, `?page=3`
- Nie przesadzaj z liczbą URLi — rate limiting chroni przed banem

### Ceneo.pl

Porównywarka cen — zbiera oferty z wielu sklepów.

```yaml
sources:
  ceneo:
    queries:
      - "nazwa produktu"
      - "marka model"
```

**Konfiguracja:** Lista zapytań tekstowych.

**Zalety:**
- Ceny z wielu sklepów
- Dobra do konkretnych produktów (znana marka + model)

### Proshop.pl

Sklep internetowy z elektroniką.

```yaml
sources:
  proshop:
    queries:
      - "nazwa produktu"
```

**Konfiguracja:** Lista zapytań tekstowych.

**Zalety:**
- Dobre ceny na elektronikę i komponenty
- Stabilny layout (rzadko się zmienia)

### Rate limiting

Wszystkie źródła mają wbudowane zabezpieczenia:
- Min. 2 sekundy między requestami
- Retry z exponential backoff przy błędach
- Graceful degradation — jedno źródło padnie → reszta działa

---

## System scoringu

### Jak działa

Scoring engine przetwarza każdą ofertę w następującej kolejności:

1. **Excluded words** → jeśli znalezione → hard reject (oferta odrzucona)
2. **Required any** → jeśli żadne nie matchuje → hard reject
3. **Score rules** → keyword w tytule/opisie → dodaje punkty
4. **Penalties** → keyword w tytule/opisie → odejmuje punkty
5. **Budget** → bonus/kara za cenę
6. **Temperatura** (tylko Pepper) → bonus/kara za społeczny dowód

### Score rules

```yaml
score_rules:
  "dokładna fraza": 50     # wysoki priorytet
  keyword: 25               # średni
  miły_bonus: 10             # niski
```

Matching jest **case-insensitive** i szuka substring w połączonym tytule + opisie oferty.

**Porady na dobry scoring:**

- **50+ punktów** — model/produkt którego szukasz dokładnie
- **25-40 punktów** — pożądane cechy (materiał, technologia)
- **10-20 punktów** — miłe dodatki
- **5-10 punktów** — drobne bonusy (stan nowy, gwarancja)

### Penalties

```yaml
penalties:
  niechciany_model: -40
  inna_kategoria: -50
  używany: -25
```

Wartości **muszą być ujemne**. Im bardziej niechciane słowo, tym większa kara.

### Required any

```yaml
required_any:
  - "12tb"
  - "12 tb"
```

Minimum **jedno** słowo z listy musi wystąpić. Inaczej oferta odrzucona. Przydatne gdy szukasz konkretnej specyfikacji (pojemność, rozmiar).

### Excluded words

```yaml
excluded_words:
  - "spam"
  - "zupelnie_inny_produkt"
```

Jeśli **którekolwiek** słowo z listy wystąpi → oferta natychmiast odrzucona. Używaj do odsiewania oczywistych pomyłek.

### Progi

```yaml
score_threshold: 50        # min. score dla alertu
score_threshold_alert: 80  # score dla "gorącej perełki"
```

**Tiery alertów:**

| Score | Tier | Emoji |
|-------|------|-------|
| ≥ `score_threshold_alert` | GORĄCA PEREŁKA | 🔥🔥🔥 |
| ≥ `score_threshold` | OKAZJA | 🔥 |
| ≥ 20 | MOŻE | 🤔 |
| < 20 | NIE PASUJE | ❌ |

### Bonus za temperaturę (Pepper)

Oferty z Pepper mają temperaturę (głosy społeczności):
- **≥ 100°** → +10 pkt (gorąca oferta, wiele osób potwierdza)
- **≥ 50°** → +5 pkt
- **< -10°** → -10 pkt (zimna, prawdopodobnie słaba oferta)

### Porady na dobry scoring

1. **Zacznij od `--verify`** — zobaczysz scoring dla wszystkich ofert
2. **Iteruj** — dostosuj punkty na podstawie wyników verify
3. **Unikaj zbyt niskiego threshold** — dostaniesz za dużo szumu
4. **Unikaj zbyt wysokiego threshold** — przegapisz dobre oferty
5. **Penalties ważniejsze niż się wydaje** — dobre penalties odsiewają śmieci skuteczniej niż dobre score_rules

---

## Custom filtry

### Kiedy potrzebne

Bazowy scoring engine wystarczy w większości przypadków. Custom filtr potrzebujesz gdy:
- Logika jest **zbyt skomplikowana** dla prostych keyword → punkty (np. rozmiary per marka roweru)
- Potrzebujesz **parsować dane** z oferty (np. wyciągnąć rozmiar z tekstu)
- Chcesz **dodatkowe reguły** zależne od kontekstu (np. kolor + rozmiar + typ)

### Jak podpiąć

1. Stwórz plik w `filters/`, np. `filters/moj_filter.py`
2. Klasa dziedziczy po `BaseFilter`:

```python
from filters.base import BaseFilter, ScoreResult

class MojFilter(BaseFilter):
    def score_deal(self, deal) -> ScoreResult:
        # Najpierw bazowy scoring (ZAWSZE wywołaj super!)
        result = super().score_deal(deal)
        if result.rejected:
            return result

        # Twoja dodatkowa logika
        custom = self.profile.get("custom_data", {})
        # ...
        return result
```

3. Zarejestruj w `filters/__init__.py`:
```python
FILTER_REGISTRY["moj_filter.MojFilter"] = MojFilter
```

4. W profilu YAML:
```yaml
custom_filter: "moj_filter.MojFilter"
custom_data:
  klucz: wartość
```

### Custom data

`custom_data` to dowolny dict przekazywany do filtra. Struktura zależy od Twojego filtra.

```yaml
custom_data:
  preferred_sizes: ["L", "XL"]
  excluded_colors:
    - "biały"
    - "żółty"
```

Dostęp w filtrze: `self.profile.get("custom_data", {})`.

---

## Powiadomienia

### Telegram

```yaml
telegram:
  topic_id: 31    # ID wątku w grupie (opcjonalne, 0 = brak wątku)
  max_alerts: 5   # Max alertów na jedno uruchomienie
```

**topic_id** — jeśli Twoja grupa Telegram ma włączone wątki (topics), podaj ID wątku. Znajdziesz go w URL: `t.me/c/GRUPAID/TOPICID`. Jeśli grupa nie ma wątków → ustaw `0` lub pomiń.

**max_alerts** — chroni przed zalewem wiadomości gdy jest dużo wyników. Najpierw wysyłane oferty z najwyższym score.

Wymagane zmienne w `.env`:
```
TELEGRAM_BOT_TOKEN=twoj_token
TELEGRAM_CHAT_ID=id_czatu_lub_grupy
```

### Notion

```yaml
# Wyłączone:
notion: null

# Włączone:
notion:
  database_id: "twoj-notion-database-id"
```

Oferty trafiają do bazy Notion jako nowe strony. Wymaga:
- Skonfigurowanego `NOTION_API_KEY_PATH` w `.env`
- Bazy Notion z odpowiednimi properties

---

## Przykłady

### Prosty profil — Słuchawki bezprzewodowe

```yaml
name: headphones
emoji: "🎧"

sources:
  pepper:
    urls:
      - "https://www.pepper.pl/search?q=słuchawki+bezprzewodowe+anc"
  ceneo:
    queries:
      - "słuchawki bezprzewodowe ANC"

budget:
  min: 200
  max: 600

score_rules:
  anc: 30
  "noise cancelling": 30
  sony: 40
  "wh-1000xm": 50
  "wf-1000xm": 45
  bose: 35
  sennheiser: 30
  "momentum": 35
  ldac: 20
  multipoint: 15
  bluetooth: 5
  aptx: 10

penalties:
  przewodowe: -50
  gamingowe: -30
  nauszne: -20       # jeśli szukasz dokanałowych
  tws: -10           # jeśli szukasz nausznych
  chiński: -20

score_threshold: 40
score_threshold_alert: 70

telegram:
  topic_id: 31
  max_alerts: 5

notion: null
```

### Średni profil — Dysk NAS 12TB

```yaml
name: nas_hdd
emoji: "💾"

sources:
  pepper:
    urls:
      - "https://www.pepper.pl/search?q=dysk+12tb+nas"
      - "https://www.pepper.pl/search?q=ironwolf+12tb"
  ceneo:
    queries:
      - "dysk HDD 12TB NAS"
      - "Seagate IronWolf 12TB"
      - "WD Red Plus 12TB"
  proshop:
    queries:
      - "HDD 12TB NAS"

budget:
  min: 400
  max: 900

score_rules:
  ironwolf: 45
  "ironwolf pro": 55
  exos: 50
  ultrastar: 50
  "red plus": 40
  "red pro": 45
  cmr: 30
  nas: 25
  7200rpm: 15
  helium: 20
  12tb: 20
  nowy: 10

penalties:
  smr: -50
  refurbished: -30
  używany: -25
  ssd: -60
  zewnętrzny: -40

required_any:
  - "12tb"
  - "12 tb"

score_threshold: 50
score_threshold_alert: 80

telegram:
  topic_id: 31
  max_alerts: 5

notion: null
```

### Zaawansowany profil — Rowery z custom filtrem

```yaml
name: bikes
emoji: "🚲"

sources:
  pepper:
    urls:
      - "https://www.pepper.pl/grupa/rowery"
      - "https://www.pepper.pl/search?q=rower+endurance"
      - "https://www.pepper.pl/search?q=rower+szosowy+carbon"

budget:
  min: 10000
  max: 15000

score_rules:
  carbon: 35
  di2: 40
  axs: 40
  endurance: 50
  gravel: 25
  domane: 45
  roubaix: 45
  ultegra: 20
  disc: 15
  tubeless: 10

penalties:
  tcr: -50
  tarmac: -50
  aeroad: -60
  madone: -50
  allez: -40

score_threshold: 70
score_threshold_alert: 120

# Custom filtr — rozszerza bazowy scoring o logikę rozmiarów i kolorów
custom_filter: "bike_filter.BikeFilter"

# Dane dla custom filtra
custom_data:
  brand_sizes:
    trek: ["l", "60", "61"]
    canyon: ["xl", "2xl"]
    giant: ["xl", "ml"]
  generic_good_sizes: ["l", "xl", "xxl", "58", "59", "60", "61", "62"]
  excluded_colors:
    - "biały"
    - "żółty"
    - "neon"
  race_keywords:
    - "aero"
    - "race"
    - "sprint"

telegram:
  topic_id: 31
  max_alerts: 5

notion:
  database_id: "twoj-notion-database-id"
```

---

## FAQ i porady

### Jak znaleźć `topic_id` na Telegramie?

Otwórz wątek w grupie Telegram (w przeglądarce lub klikając link). URL wygląda tak:
`https://t.me/c/1234567890/31` — ostatnia liczba (31) to `topic_id`.

### Ile źródeł powinienem użyć?

Zależy od produktu:
- **Okazje/promocje** → Pepper (społeczność filtruje za Ciebie)
- **Porównywanie cen** → Ceneo (wiele sklepów)
- **Konkretny sklep** → Proshop
- **Najlepsze pokrycie** → wszystkie trzy

### Dlaczego oferta ma niski score mimo że jest dobra?

Sprawdź `--verify`:
```bash
python deal_hunter.py --profile moj_profil --verify
```

Częste przyczyny:
- Brak keywordu w `score_rules` (dodaj go)
- Penalty niezamierzenie matchuje (np. "blue" w nazwie niebieskiego modelu)
- Oferta poza budżetem
- `required_any` nie matchuje (sprawdź pisownię/warianty)

### Jak ustawić dobre progi?

1. Uruchom `--verify` i zobacz rozkład score'ów
2. `score_threshold` ustaw tak aby odciąć szum (dolne ~30% ofert)
3. `score_threshold_alert` ustaw na top ~10% — to będą Twoje "gorące perełki"
4. Lepiej zacząć od niższych progów i podnieść niż przegapić dobrą ofertę

### Czy mogę mieć profil bez penalties?

Tak — `penalties` może być pusty (`penalties: {}`), ale tracisz ważne narzędzie do odsiewania śmieci. Zalecam dodać choćby kilka oczywistych wykluczeń.

### Jak testować profil bez wysyłania alertów?

Użyj flagi `--verify`:
```bash
python deal_hunter.py --profile moj_profil --verify
```

Wyświetla WSZYSTKIE znalezione oferty z pełnym breakdownem scoringu, bez zapisywania stanu i bez wysyłania powiadomień.

### Mogę użyć wielu URLi Pepper?

Tak, im więcej tym lepsze pokrycie. Ale pamiętaj o rate limitingu — nie przesadzaj (10-15 URLi to sensowny maks).

### Jak działa deduplikacja?

Deal Hunter zapisuje state per profil w `state/`. Każda oferta identyfikowana przez `{source}:{native_id}`. State ma TTL 14 dni — po tym czasie oferta może ponownie zalerować (prawdopodobnie już nieaktualna).

Dodatkowo jest cross-source deduplikacja po `title + price` — ta sama oferta z Pepper i Ceneo nie zaleruje dwa razy.
