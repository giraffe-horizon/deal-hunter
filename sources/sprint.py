"""Sprint-Rowery.pl source — bike shop scraper with pagination."""

import json
import logging
import re

from bs4 import BeautifulSoup

from .base import Deal, Source

logger = logging.getLogger(__name__)


class SprintSource(Source):
    """Scrapes product listings from Sprint-Rowery.pl with pagination."""

    SOURCE_NAME = "sprint"
    BASE_URL = "https://sprint-rowery.pl"

    def fetch_deals(self, config: dict) -> list[Deal]:
        urls: list[str] = config.get("urls", [])
        if not urls:
            logger.warning("Sprint: no urls configured")
            return []

        max_pages: int = config.get("max_pages", 5)
        all_deals: list[Deal] = []

        for base_url in urls:
            for page in range(1, max_pages + 1):
                url = base_url if page == 1 else f"{base_url}?page={page}"
                html_text = self._fetch_page(url)
                if not html_text:
                    logger.warning(f"Sprint: failed to fetch page {page} of {base_url}")
                    break

                deals = self._parse_page(html_text, url)
                if not deals:
                    logger.debug(f"Sprint: no deals on page {page} of {base_url}, stopping")
                    break

                all_deals.extend(deals)
                logger.info(f"Sprint: parsed {len(deals)} deals from {url}")

        return all_deals

    def _parse_page(self, html_text: str, url: str) -> list[Deal]:
        # Strategy 1: JSON-LD
        deals = self._parse_jsonld(html_text, url)
        if deals:
            return deals
        # Strategy 2: HTML product cards
        return self._parse_html(html_text, url)

    def _parse_jsonld(self, html_text: str, url: str) -> list[Deal]:
        soup = BeautifulSoup(html_text, "html.parser")
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
                logger.debug(f"Sprint JSON-LD parse error: {e}")
                continue

        return deals

    def _jsonld_to_deal(self, product: dict, url: str) -> Deal | None:
        try:
            name = product.get("name", "").strip()
            if not name:
                return None

            link = product.get("url", url)
            if not link.startswith("http"):
                link = f"{self.BASE_URL}{link}"

            price = 0
            regular_price = 0
            offers = product.get("offers", {})
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            if offers:
                price = int(float(offers.get("price", 0)))

            image_url = product.get("image", "")
            if isinstance(image_url, list):
                image_url = image_url[0] if image_url else ""

            native_id = product.get("sku", product.get("productID", ""))
            if not native_id:
                m = re.search(r"/(\d+)", link)
                native_id = m.group(1) if m else re.sub(r"\W+", "_", name[:60])

            description = product.get("description", f"Sprint: {url}")

            return Deal(
                id=f"sprint:{native_id}",
                title=name,
                price=price,
                link=link,
                source=self.SOURCE_NAME,
                description=description,
                temperature=0,
                image_url=image_url,
                published_at="",
                regular_price=regular_price,
            )
        except Exception as e:
            logger.debug(f"Sprint JSON-LD deal error: {e}")
            return None

    def _parse_html(self, html_text: str, url: str) -> list[Deal]:
        """Fallback: parse HTML product cards."""
        soup = BeautifulSoup(html_text, "html.parser")
        deals: list[Deal] = []

        products = soup.find_all(
            "div",
            class_=re.compile(
                r"product-item|product-card|product-miniature|product-thumb|product-box"
            ),
        )
        if not products:
            products = soup.find_all("article", class_=re.compile(r"product"))
        if not products:
            products = soup.find_all("li", class_=re.compile(r"product"))

        for prod in products:
            deal = self._parse_html_product(prod, url)
            if deal:
                deals.append(deal)

        return deals

    def _parse_html_product(self, prod, url: str) -> Deal | None:
        try:
            # Title
            title_tag = prod.find(class_=re.compile(r"product-title|product-name|name"))
            if not title_tag:
                title_tag = prod.find(["h2", "h3", "h4"])
            if title_tag:
                link_inner = title_tag.find("a")
                if link_inner:
                    title_tag = link_inner
            if not title_tag:
                for a in prod.find_all("a", href=True):
                    text = a.get_text().strip()
                    if len(text) > 10:
                        title_tag = a
                        break
            if not title_tag:
                return None

            title = title_tag.get_text().strip()
            if not title:
                return None

            href = title_tag.get("href", "")
            if not href:
                link_el = prod.find("a", href=True)
                href = link_el.get("href", "") if link_el else ""
            link = href if href.startswith("http") else f"{self.BASE_URL}{href}" if href else url

            # Price
            price = 0
            regular_price = 0
            price_tag = prod.find(
                class_=re.compile(r"price-new|price-current|current-price|price-sale|price")
            )
            if price_tag:
                price = self._extract_price(price_tag.get_text())

            old_tag = prod.find(
                class_=re.compile(r"price-old|regular-price|old-price|price-regular")
            )
            if old_tag:
                regular_price = self._extract_price(old_tag.get_text())

            if not price:
                all_prices = prod.find_all(class_=re.compile(r"price"))
                for p in all_prices:
                    val = self._extract_price(p.get_text())
                    if val:
                        price = val
                        break

            # Image
            image_url = ""
            img = prod.find("img")
            if img:
                image_url = img.get("src", "") or img.get("data-src", "")
                if image_url and not image_url.startswith("http"):
                    image_url = f"{self.BASE_URL}{image_url}"

            # ID
            native_id = prod.get("data-id", "") or prod.get("data-product-id", "")
            if not native_id and href:
                m = re.search(r"/(\d+)", href)
                native_id = m.group(1) if m else ""
            if not native_id:
                native_id = re.sub(r"\W+", "_", title[:60])

            return Deal(
                id=f"sprint:{native_id}",
                title=title,
                price=price,
                link=link,
                source=self.SOURCE_NAME,
                description=f"Sprint: {url}",
                temperature=0,
                image_url=image_url,
                published_at="",
                regular_price=regular_price,
            )
        except Exception as e:
            logger.debug(f"Sprint HTML parse error: {e}")
            return None

    @staticmethod
    def _extract_price(text: str) -> int:
        text = text.replace("\xa0", "").replace(" ", "").replace(",", ".")
        m = re.search(r"(\d[\d\s]*(?:[.,]\d{1,2})?)", text)
        if m:
            digits = re.sub(r"[^\d.]", "", m.group(1))
            try:
                return int(float(digits))
            except ValueError:
                pass
        return 0
