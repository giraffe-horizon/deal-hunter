"""Universal YAML-driven source engine.

Loads store definitions from stores/*.yaml and scrapes using configured strategies:
- CSS selectors (primary)
- JSON-LD (schema.org Product / ItemList)
- GTM dataLayer (data-gtm-impression attributes)
"""

import contextlib
import html as html_lib
import json
import logging
import re
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, urlencode, urljoin, urlparse, urlunparse

import yaml
from bs4 import BeautifulSoup

from .base import Deal, Source

logger = logging.getLogger(__name__)

STORES_DIR = Path(__file__).parent.parent / "stores"


def load_store_definition(name: str) -> dict | None:
    """Load a single store YAML definition by name."""
    path = STORES_DIR / f"{name}.yaml"
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        return dict(yaml.safe_load(f))


def load_all_store_definitions() -> dict[str, dict]:
    """Load all store YAML definitions from stores/ directory."""
    stores: dict[str, dict] = {}
    if not STORES_DIR.exists():
        return stores
    for path in sorted(STORES_DIR.glob("*.yaml")):
        try:
            with path.open(encoding="utf-8") as f:
                store_def = yaml.safe_load(f)
            if isinstance(store_def, dict) and "name" in store_def:
                strategies = store_def.get("strategies", ["css"])
                selectors = store_def.get("selectors", {})
                if "css" in strategies and (
                    not isinstance(selectors, dict) or not selectors.get("products")
                ):
                    logger.warning(
                        f"Store '{store_def['name']}' uses css strategy but missing "
                        f"selectors.products, skipping: {path}"
                    )
                    continue
                stores[store_def["name"]] = store_def
            else:
                logger.warning(f"Invalid store definition (missing 'name'): {path}")
        except Exception as e:
            logger.warning(f"Failed to load store definition {path}: {e}")
    return stores


def make_yaml_source_class(store_def: dict) -> type["YamlSource"]:
    """Create a YamlSource subclass with a baked-in store definition."""
    cls_name = store_def["name"].replace("-", "_").title().replace("_", "") + "YamlSource"
    return type(cls_name, (YamlSource,), {"_store_def": store_def})


class YamlSource(Source):
    """Universal source engine driven by YAML store definitions.

    Supports catalog-type (direct URLs) and search-type (query-based) stores,
    with pluggable parsing strategies: CSS selectors, JSON-LD, GTM dataLayer.
    """

    _store_def: dict = {}

    def __init__(self, store_def: dict | None = None) -> None:
        super().__init__()
        if store_def is not None:
            self._store_def = store_def

    @property
    def _store_name(self) -> str:
        return str(self._store_def.get("name", "yaml"))

    @property
    def _base_url(self) -> str:
        return str(self._store_def.get("base_url", ""))

    def fetch_deals(self, config: dict) -> list[Deal]:
        store_type = self._store_def.get("type", "catalog")
        if store_type == "search":
            return self._fetch_search(config)
        return self._fetch_catalog(config)

    # ── Search-type stores ──

    def _fetch_search(self, config: dict) -> list[Deal]:
        queries: list[str] = config.get("queries", [])
        if not queries:
            logger.warning(f"{self._store_name}: no queries configured")
            return []

        category: str = config.get("category", "")
        all_deals: list[Deal] = []

        for query in queries:
            url = self._build_search_url(query, category)
            html = self._fetch_page(url)
            if html:
                deals = self._parse_page(html, url)
                all_deals.extend(deals)
                logger.info(f"{self._store_name}: parsed {len(deals)} deals for query '{query}'")
            else:
                logger.error(f"{self._store_name}: failed to fetch results for '{query}'")

        return all_deals

    def _build_search_url(self, query: str, category: str = "") -> str:
        encoded = quote_plus(query)
        if category and "search_url_category" in self._store_def:
            template = self._store_def["search_url_category"]
        else:
            template = self._store_def.get("search_url", "")
        return str(template).replace("{query}", encoded).replace("{category}", category)

    # ── Catalog-type stores ──

    def _fetch_catalog(self, config: dict) -> list[Deal]:
        urls: list[str] = config.get("urls", [])
        if not urls:
            logger.warning(f"{self._store_name}: no urls configured")
            return []

        pagination = self._store_def.get("pagination")
        max_pages = config.get("max_pages", pagination.get("max_pages", 5) if pagination else 1)
        all_deals: list[Deal] = []

        for base_url in urls:
            if pagination:
                for page in range(1, max_pages + 1):
                    url = self._paginate_url(base_url, page, pagination)
                    html = self._fetch_page(url)
                    if not html:
                        logger.warning(
                            f"{self._store_name}: failed to fetch page {page} of {base_url}"
                        )
                        break
                    deals = self._parse_page(html, url)
                    if not deals:
                        logger.debug(
                            f"{self._store_name}: no deals on page {page}, stopping pagination"
                        )
                        break
                    all_deals.extend(deals)
                    logger.info(f"{self._store_name}: parsed {len(deals)} deals from {url}")
            else:
                html = self._fetch_page(base_url)
                if html:
                    deals = self._parse_page(html, base_url)
                    all_deals.extend(deals)
                    logger.info(f"{self._store_name}: parsed {len(deals)} deals from {base_url}")
                else:
                    logger.error(f"{self._store_name}: failed to fetch {base_url}")

        return all_deals

    @staticmethod
    def _paginate_url(base_url: str, page: int, pagination: dict) -> str:
        if page == 1:
            return base_url
        param = pagination.get("param", "page")
        parsed = urlparse(base_url)
        params = parse_qs(parsed.query)
        params[param] = [str(page)]
        return urlunparse(parsed._replace(query=urlencode(params, doseq=True)))

    # ── Page parsing (strategy dispatch) ──

    def _parse_page(self, html: str, url: str) -> list[Deal]:
        """Parse a page using configured strategies in order. First with results wins."""
        strategies = self._store_def.get("strategies", ["css"])
        for strategy in strategies:
            if strategy == "json-ld":
                deals = self._parse_jsonld(html, url)
            elif strategy == "gtm":
                deals = self._parse_gtm(html, url)
            elif strategy == "css":
                deals = self._parse_css(html, url)
            else:
                logger.warning(f"{self._store_name}: unknown strategy '{strategy}'")
                continue
            if deals:
                return deals
        return []

    # ── CSS strategy ──

    def _parse_css(self, html: str, url: str) -> list[Deal]:
        soup = BeautifulSoup(html, "html.parser")
        selectors = self._store_def.get("selectors", {})
        products_sel = selectors.get("products", "")
        if not products_sel:
            return []

        products = soup.select(products_sel)
        deals: list[Deal] = []
        for prod in products:
            deal = self._extract_deal_css(prod, url, selectors)
            if deal:
                deals.append(deal)
        return deals

    def _extract_deal_css(self, prod, url: str, selectors: dict) -> Deal | None:
        try:
            title = self._extract_field(prod, selectors.get("title", ""))
            if not title:
                return None

            price_text = self._extract_field(prod, selectors.get("price", ""))
            price = self.extract_price(price_text) if price_text else 0

            link = self._extract_field(prod, selectors.get("link", ""))
            link = self._resolve_url(link, url)

            image = self._extract_field(prod, selectors.get("image", ""))
            if image:
                image = self._resolve_url(image, url)

            description = self._extract_field(prod, selectors.get("description", ""))

            regular_price = 0
            rp_sel = selectors.get("regular_price", "")
            if rp_sel:
                rp_text = self._extract_field(prod, rp_sel)
                regular_price = self.extract_price(rp_text) if rp_text else 0

            native_id = self._extract_native_id(prod, link, title, selectors)

            return Deal(
                id=f"{self._store_name}:{native_id}",
                title=title.strip(),
                price=price,
                link=link or url,
                source=self._store_name,
                description=description or "",
                temperature=0,
                image_url=image or "",
                published_at="",
                regular_price=regular_price,
            )
        except Exception as e:
            logger.debug(f"{self._store_name} CSS parse error: {e}")
            return None

    # ── JSON-LD strategy ──

    def _parse_jsonld(self, html: str, url: str) -> list[Deal]:
        soup = BeautifulSoup(html, "html.parser")
        deals: list[Deal] = []

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                if isinstance(data, list):
                    for item in data:
                        t = item.get("@type", "")
                        if t in ("ItemList", "Product"):
                            data = item
                            break
                    else:
                        continue

                item_type = data.get("@type", "")
                if item_type == "ItemList":
                    for item in data.get("itemListElement", []):
                        product = item.get("item", item)
                        deal = self._jsonld_to_deal(product, url)
                        if deal:
                            deals.append(deal)
                elif item_type == "Product":
                    deal = self._jsonld_to_deal(data, url)
                    if deal:
                        deals.append(deal)
            except (json.JSONDecodeError, TypeError, KeyError) as e:
                logger.debug(f"{self._store_name} JSON-LD parse error: {e}")
                continue

        return deals

    def _jsonld_to_deal(self, product: dict, url: str) -> Deal | None:
        try:
            name = product.get("name", "").strip()
            if not name:
                return None

            link = product.get("url", url)
            if not link.startswith("http"):
                link = f"{self._base_url}{link}" if self._base_url else link

            price = 0
            regular_price = 0
            offers = product.get("offers", {})
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            if offers:
                price = int(float(offers.get("price", 0)))
                high_price = int(float(offers.get("highPrice", 0)))
                if high_price > price:
                    regular_price = high_price

            image_url = product.get("image", "")
            if isinstance(image_url, list):
                image_url = image_url[0] if image_url else ""

            native_id = product.get("sku", product.get("productID", ""))
            if not native_id:
                matches = re.findall(r"/(\d+)", link)
                native_id = matches[-1] if matches else re.sub(r"\W+", "_", name[:60])

            description = product.get("description", "")

            return Deal(
                id=f"{self._store_name}:{native_id}",
                title=name,
                price=price,
                link=link,
                source=self._store_name,
                description=description or f"{self._store_name}: {url}",
                temperature=0,
                image_url=image_url,
                published_at="",
                regular_price=regular_price,
            )
        except Exception as e:
            logger.debug(f"{self._store_name} JSON-LD deal error: {e}")
            return None

    # ── GTM dataLayer strategy ──

    def _parse_gtm(self, html_text: str, url: str) -> list[Deal]:
        soup = BeautifulSoup(html_text, "html.parser")
        deals: list[Deal] = []

        elements = soup.find_all(attrs={"data-gtm-impression": True})
        for el in elements:
            try:
                raw = html_lib.unescape(el.get("data-gtm-impression", ""))
                data = json.loads(raw)
                deal = self._gtm_to_deal(data, el, url)
                if deal:
                    deals.append(deal)
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.debug(f"{self._store_name} GTM parse error: {e}")
                continue

        return deals

    def _gtm_to_deal(self, data: dict, el, url: str) -> Deal | None:
        try:
            name = data.get("name", "").strip()
            if not name:
                return None

            native_id = str(data.get("id", data.get("sku", name[:50])))
            price = int(float(data.get("price", 0)))

            # Regular price from discount
            regular_price = 0
            discount = data.get("discount", data.get("metric4", 0))
            if discount and price:
                with contextlib.suppress(ValueError, TypeError):
                    regular_price = price + int(float(discount))

            # Description from GTM metadata
            desc_parts = []
            variant = data.get("variant", "")
            dimension = data.get("dimension54", data.get("dimension50", ""))
            color = variant or dimension
            if color:
                desc_parts.append(f"Color: {color}")
            category = data.get("category", "")
            if category:
                desc_parts.append(category)
            description = " | ".join(desc_parts) if desc_parts else f"{self._store_name}: {url}"

            # Link
            link_tag = el.find("a", href=True)
            link = ""
            if link_tag:
                href = link_tag.get("href", "")
                link = href if href.startswith("http") else f"{self._base_url}{href}"
            if not link:
                link = url

            # Image
            image_url = ""
            img = el.find("img")
            if img:
                image_url = img.get("src", "") or img.get("data-src", "")
                if image_url and not image_url.startswith("http"):
                    image_url = f"{self._base_url}{image_url}"

            return Deal(
                id=f"{self._store_name}:{native_id}",
                title=name,
                price=price,
                link=link,
                source=self._store_name,
                description=description,
                temperature=0,
                image_url=image_url,
                published_at="",
                regular_price=regular_price,
            )
        except Exception as e:
            logger.debug(f"{self._store_name} GTM deal error: {e}")
            return None

    # ── Field extraction helpers ──

    @staticmethod
    def _extract_field(container, selector: str) -> str:
        """Extract text or attribute from a container using CSS selectors.

        Supports:
        - ``a@href`` — find <a>, get href attribute
        - ``@data-pid`` — get data-pid from the container itself
        - Comma-separated fallbacks: ``span.a, span.b`` — try each until found
        """
        if not selector:
            return ""

        for sel in selector.split(","):
            sel = sel.strip()
            if not sel:
                continue

            if "@" in sel:
                parts = sel.split("@", 1)
                css_sel = parts[0].strip()
                attr = parts[1].strip()
                el = container.select_one(css_sel) if css_sel else container
                if el:
                    val = el.get(attr, "")
                    if val:
                        return str(val)
            else:
                el = container.select_one(sel)
                if el:
                    text = el.get_text(strip=True)
                    if text:
                        return str(text)

        return ""

    def _resolve_url(self, url: str, page_url: str) -> str:
        """Resolve a possibly-relative URL against the store base or page URL."""
        if not url:
            return ""
        if url.startswith("http"):
            return url
        base = self._base_url or page_url
        if url.startswith("/"):
            if base:
                parsed = urlparse(base)
                return f"{parsed.scheme}://{parsed.netloc}{url}"
            return url
        return urljoin(base, url)

    @staticmethod
    def _extract_native_id(prod, link: str, title: str, selectors: dict) -> str:
        """Extract a native product ID using selector, link, or title fallback."""
        # Try ID selector (e.g., @data-pid)
        id_sel = selectors.get("id", "")
        if id_sel:
            native_id = YamlSource._extract_field(prod, id_sel)
            if native_id:
                return native_id

        # Try to extract from link (use last digit segment)
        if link:
            matches = re.findall(r"/(\d+)", link)
            if matches:
                return str(matches[-1])

        # Fallback to sanitized title
        return re.sub(r"\W+", "_", title[:60])
