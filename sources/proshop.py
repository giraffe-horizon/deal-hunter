"""Proshop.pl source — online store scraper."""

import logging
import re
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from .base import Deal, Source

logger = logging.getLogger(__name__)


class ProshopSource(Source):
    """Scrapes product listings from Proshop.pl search results."""

    SOURCE_NAME = "proshop"
    BASE_URL = "https://www.proshop.pl"

    def fetch_deals(self, config: dict) -> list[Deal]:
        """Fetch deals from Proshop search.

        Args:
            config: Profile source config with 'queries' and optional 'category' keys.
        """
        queries: list[str] = config.get("queries", [])
        if not queries:
            logger.warning("Proshop: no queries configured")
            return []

        all_deals: list[Deal] = []
        category: str = config.get("category", "")

        for query in queries:
            encoded = quote_plus(query)
            if category:
                url = f"{self.BASE_URL}/{category}?pre_search=1&search={encoded}"
            else:
                url = f"{self.BASE_URL}/Search?search={encoded}"

            html = self._fetch_page(url)
            if html:
                deals = self._parse_results(html, query)
                all_deals.extend(deals)
                logger.info(f"Proshop: parsed {len(deals)} deals for query '{query}'")
            else:
                logger.error(f"Proshop: failed to fetch results for '{query}'")

        return all_deals

    def _parse_results(self, html: str, query: str) -> list[Deal]:
        """Parse Proshop search results page."""
        soup = BeautifulSoup(html, "html.parser")
        deals: list[Deal] = []

        # Try different product listing selectors
        products = soup.select(
            "[data-product-id], .product-list__item, #products .product, "
            ".product-list .product-item"
        )
        if not products:
            products = soup.find_all("div", id=re.compile(r"product_\d+"))
        if not products:
            products = soup.find_all("li", class_=re.compile(r"product"))
        if not products:
            products = soup.find_all("div", class_=re.compile(r"product"))

        for prod in products:
            deal = self._parse_product(prod, query)
            if deal:
                deals.append(deal)

        return deals

    def _parse_product(self, prod, query: str) -> Deal | None:
        """Parse a single product item."""
        try:
            # Title
            title_tag = prod.find("a", class_=re.compile(r"site-product-link|product-title"))
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
            href = title_tag.get("href", "")
            link = href if href.startswith("http") else f"{self.BASE_URL}{href}" if href else ""

            # Price — Proshop uses 'site-currency-lg', 'site-currency-attention', etc.
            price = 0
            price_tag = prod.find(
                class_=re.compile(
                    r"site-currency-lg|site-currency-attention|site-currency-sm|"
                    r"product-price|price-value"
                )
            )
            if not price_tag:
                price_tag = prod.find(class_=re.compile(r"price|currency"))
            if not price_tag:
                price_tag = prod.find("span", class_=re.compile(r"price"))
            if price_tag:
                price = self._extract_price(price_tag.get_text())

            # Image
            image_url = ""
            img = prod.find("img")
            if img:
                image_url = img.get("src", "") or img.get("data-src", "")
                if image_url and not image_url.startswith("http"):
                    image_url = f"{self.BASE_URL}{image_url}"

            # Product ID
            native_id = prod.get("data-product-id", "") or prod.get("id", "")
            if not native_id and href:
                m = re.search(r"/(\d+)", href)
                native_id = m.group(1) if m else ""
            if not native_id:
                native_id = re.sub(r"\W+", "_", title[:60])

            if not title:
                return None

            return Deal(
                id=f"proshop:{native_id}",
                title=title,
                price=price,
                link=link,
                source=self.SOURCE_NAME,
                description=f"Proshop search: {query}",
                temperature=0,
                image_url=image_url,
                published_at="",
            )
        except Exception as e:
            logger.debug(f"Proshop parse error: {e}")
            return None

    @staticmethod
    def _extract_price(text: str) -> int:
        """Extract integer price from text."""
        text = text.replace("\xa0", "").replace(" ", "").replace(",", ".")
        m = re.search(r"(\d[\d\s]*(?:[.,]\d{1,2})?)", text)
        if m:
            digits = re.sub(r"[^\d.]", "", m.group(1))
            try:
                return int(float(digits))
            except ValueError:
                pass
        return 0
