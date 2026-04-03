# Adding a New Store

Adding a store to Deal Hunter takes ~5 minutes and **zero Python knowledge**. Just create a YAML file.

## Quick Start

1. Create `stores/mystore.yaml`
2. Define selectors (see examples below)
3. Test: `python deal_hunter.py --profile your_profile --verify`

## Minimal Example (catalog store)

```yaml
name: mystore
base_url: https://mystore.com

selectors:
  products: ".product-card"
  title: "h3.product-name"
  price: ".price"
  link: "a @href"
  image: "img @src"
```

That's it. The engine handles fetching, rate limiting, price parsing, and dedup.

## Search Store (like Ceneo)

```yaml
name: mystore
type: search
base_url: https://mystore.com
search_url: "https://mystore.com/search?q={query}"

selectors:
  products: ".result-item"
  title: ".item-name"
  price: ".item-price"
  link: ".item-name a @href"
  image: ".item-img img @src"
```

Use `{query}` in `search_url` — it gets replaced with the search term from the profile.

## Pagination

```yaml
pagination:
  param: page        # adds ?page=2, ?page=3, etc.
  max_pages: 5       # stop after 5 pages (default)
```

## Price Parsing

Default handles European format (`1 299,00 zł` → `1299`). Override if needed:

```yaml
price_format:
  decimal: ","
  thousands: " "
  currency_strip: ["zł", "PLN", "€"]
```

## Parsing Strategies

The engine tries strategies in order. First one that returns results wins:

```yaml
strategies:
  - json-ld    # Schema.org Product objects from <script type="application/ld+json">
  - css        # CSS selectors defined above
  - gtm        # Google Tag Manager dataLayer product impressions
```

Default: `[css]`. Most stores with structured data work great with `[json-ld, css]`.

## Attribute Selectors

Use `@attr` to extract attributes instead of text:

- `"a @href"` → extracts the `href` attribute
- `"img @src"` → extracts the `src` attribute
- `"img @data-src"` → extracts `data-src` (lazy loading)
- `".price"` → extracts text content (no `@`)

Comma-separated fallbacks: `"img @data-src, img @src"` tries `data-src` first.

## Using Your Store in a Profile

```yaml
# profiles/my_search.yaml
name: My Product Search
sources:
  mystore:
    urls:
      - "https://mystore.com/category/deals"
```

Or for search-type stores:

```yaml
sources:
  mystore:
    queries:
      - "wireless headphones"
      - "bluetooth speaker"
```

## Tips

- **Find selectors:** Open the store in Chrome → right-click a product → Inspect → copy CSS selector
- **Test one URL first** before adding multiple
- **JSON-LD is your friend** — most modern stores have it, and it's more reliable than CSS selectors
- **Check existing stores** in this directory for real-world examples
