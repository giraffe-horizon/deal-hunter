# Adding a Store

Adding a new store to Deal Hunter takes ~5 minutes. You create a YAML file — no Python needed.

## How It Works

Deal Hunter auto-discovers YAML files in the `stores/` directory at startup. Each file defines:
- Where to find products on a page (CSS selectors)
- How to extract title, price, link, image
- What parsing strategies to use

## Step-by-Step

### 1. Find the selectors

Open the store in Chrome → go to a product listing page → right-click a product → **Inspect**.

You need to find CSS selectors for:
- **Product container** — the repeating element wrapping each product
- **Title** — product name (usually an `<a>` or `<h2>`)
- **Price** — current price
- **Link** — URL to the product page
- **Image** — product image

### 2. Create the YAML file

```yaml
# stores/mystore.yaml
name: mystore
base_url: https://mystore.com

selectors:
  products: ".product-card"        # container for each product
  title: "h3.product-name"        # product title text
  price: ".price"                  # price text (auto-parsed)
  link: "a@href"                   # link URL (@ extracts attribute)
  image: "img@src"                 # image URL
```

That's it for a basic store.

### 3. Test it

Add to a profile and verify:

```yaml
# profiles/test.yaml
name: Test
sources:
  mystore:
    urls:
      - "https://mystore.com/category/deals"
scoring:
  score_rules: {}
  budget_min: 0
  budget_max: 99999
  thresholds:
    hot: 30
    good: 15
    meh: 0
```

```bash
python deal_hunter.py --profile test --verify
```

## Advanced Features

### Search-type stores (like Ceneo)

For stores with a search endpoint:

```yaml
name: mystore
type: search
base_url: https://mystore.com
search_url: "https://mystore.com/search?q={query}"

selectors:
  products: ".search-result"
  title: ".result-title"
  price: ".result-price"
  link: ".result-title a@href"
  image: ".result-img img@src"
```

Use `{query}` placeholder — it gets replaced with search terms from the profile. Optional `{category}` placeholder works too.

### Fallback selectors

Sites change their HTML. Use comma-separated selectors — first match wins:

```yaml
selectors:
  price: ".price-new, .price-current, .price"
  image: "img@data-lazy-src, img@data-src, img@src"
```

### Attribute extraction

- `"a@href"` — extracts `href` attribute
- `"img@src"` — extracts `src` attribute
- `"div@data-price"` — extracts any `data-` attribute
- `".price"` — extracts text content (no `@`)

### Pagination

```yaml
pagination:
  param: page          # adds ?page=2, ?page=3...
  max_pages: 5         # stop after N pages
```

### Parsing Strategies

The engine tries strategies in order. First with results wins:

```yaml
strategies:
  - json-ld    # Schema.org Product from <script type="application/ld+json">
  - css        # CSS selectors (defined above)
  - gtm        # Google Tag Manager dataLayer impressions
```

Default: `[css]`. Tip: most modern stores have JSON-LD — try `[json-ld, css]` for more reliable parsing.

### Optional selectors

```yaml
selectors:
  # ... required ones ...
  description: ".product-description"     # deal description
  regular_price: ".price-old, .was-price" # original price (for discount detection)
  id: "@data-product-id"                  # native product ID
```

## Real Examples

Check `stores/*.yaml` in the repo for working examples:

| Store | Type | Strategies | Notes |
|-------|------|-----------|-------|
| ceneo.yaml | search | css | Price comparison, multiple layouts |
| canyon.yaml | catalog | gtm, css | Uses GTM dataLayer |
| rowertour.yaml | catalog | json-ld, css | JSON-LD primary |
| veloshop.yaml | catalog | css | Simple OpenCart store |
| sprint.yaml | catalog | json-ld, css | With pagination |

## Tips

- **Start with JSON-LD** — it's more stable than CSS selectors across site redesigns
- **Test one URL** before adding multiple
- **Use `--verify`** to see parsed results without notifications
- **Check existing stores** for patterns similar to your target site
