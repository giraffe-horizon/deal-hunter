"""Ceneo.pl source — product price comparison scraper."""

import re
import logging
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from .base import Source, Deal

logger = logging.getLogger(__name__)


class CeneoSource(Source):
    """Scrapes product listings from Ceneo.pl search results."""

    SOURCE_NAME = "ceneo"
    BASE_URL = "https://www.ceneo.pl"

    def fetch_deals(self, config: dict) -> list[Deal]:
        """Fetch deals from Ceneo search.

        Args:
            config: Profile source config with 'queries' and optional 'category' keys.
        """
        queries: list[str] = config.get("queries", [])
        if not queries:
            logger.warning("Ceneo: no queries configured")
            return []

        all_deals: list[Deal] = []
        category: str = config.get("category", "")

        for query in queries:
            encoded = quote_plus(query)
            if category:
                url = f"{self.BASE_URL}/{category};szukaj-{encoded}"
            else:
                url = f"{self.BASE_URL}/;szukaj-{encoded}"

            html = self._fetch_page(url)
            if html:
                deals = self._parse_results(html, query)
                all_deals.extend(deals)
                logger.info(f"Ceneo: parsed {len(deals)} deals for query '{query}'")
            else:
                logger.error(f"Ceneo: failed to fetch results for '{query}'")

        return all_deals

    def _parse_results(self, html: str, query: str) -> list[Deal]:
        """Parse Ceneo search results page."""
        soup = BeautifulSoup(html, 'html.parser')
        deals: list[Deal] = []

        # Ceneo product listing items
        products = soup.find_all('div', class_=re.compile(r'cat-prod-row|product-row'))
        if not products:
            products = soup.find_all('li', class_=re.compile(r'cat-prod'))
        if not products:
            products = soup.select('.category-list-body .cat-prod-row')

        for prod in products:
            deal = self._parse_product(prod, query)
            if deal:
                deals.append(deal)

        # Also try the grid/card layout
        if not deals:
            cards = soup.find_all('div', {'class': re.compile(r'product-card|grid-item')})
            for card in cards:
                deal = self._parse_card(card, query)
                if deal:
                    deals.append(deal)

        return deals

    def _parse_product(self, prod, query: str) -> Deal | None:
        """Parse a single product row."""
        try:
            # Title
            title_tag = prod.find('a', class_=re.compile(r'product-name|go-to-product'))
            if not title_tag:
                title_tag = prod.find('strong', class_=re.compile(r'cat-prod-row__name'))
                if title_tag:
                    title_tag = title_tag.find('a') or title_tag

            if not title_tag:
                return None

            title = title_tag.get_text().strip()
            href = title_tag.get('href', '')
            link = href if href.startswith('http') else f"{self.BASE_URL}{href}" if href else ""

            # Price
            price = 0
            price_tag = prod.find('span', class_=re.compile(r'price|value'))
            if not price_tag:
                price_tag = prod.find('div', class_=re.compile(r'price'))
            if price_tag:
                price = self._extract_price(price_tag.get_text())

            # Image
            image_url = ""
            img = prod.find('img')
            if img:
                image_url = img.get('data-original', '') or img.get('src', '') or img.get('data-src', '')

            # Product ID from data attribute or href
            native_id = prod.get('data-pid', '') or prod.get('data-productid', '')
            if not native_id and href:
                m = re.search(r'/(\d+)', href)
                native_id = m.group(1) if m else title[:50]
            if not native_id:
                native_id = title[:50]

            if not title or not link:
                return None

            return Deal(
                id=f"ceneo:{native_id}",
                title=title,
                price=price,
                link=link,
                source=self.SOURCE_NAME,
                description=f"Ceneo search: {query}",
                temperature=0,
                image_url=image_url,
                published_at="",
            )
        except Exception as e:
            logger.debug(f"Ceneo parse error: {e}")
            return None

    def _parse_card(self, card, query: str) -> Deal | None:
        """Parse a product card (grid layout)."""
        try:
            title_el = card.find(['a', 'span', 'strong'], class_=re.compile(r'name|title|product'))
            if not title_el:
                return None

            title = title_el.get_text().strip()
            link_el = card.find('a', href=True)
            href = link_el.get('href', '') if link_el else ''
            link = href if href.startswith('http') else f"{self.BASE_URL}{href}" if href else ""

            price = 0
            price_el = card.find(class_=re.compile(r'price|value'))
            if price_el:
                price = self._extract_price(price_el.get_text())

            image_url = ""
            img = card.find('img')
            if img:
                image_url = img.get('data-original', '') or img.get('src', '')

            native_id = title[:50]
            if href:
                m = re.search(r'/(\d+)', href)
                if m:
                    native_id = m.group(1)

            if not title:
                return None

            return Deal(
                id=f"ceneo:{native_id}",
                title=title,
                price=price,
                link=link,
                source=self.SOURCE_NAME,
                description=f"Ceneo search: {query}",
                temperature=0,
                image_url=image_url,
                published_at="",
            )
        except Exception as e:
            logger.debug(f"Ceneo card parse error: {e}")
            return None

    @staticmethod
    def _extract_price(text: str) -> int:
        """Extract integer price from text."""
        text = text.replace('\xa0', '').replace(' ', '').replace(',', '.')
        m = re.search(r'(\d[\d\s]*(?:[.,]\d{1,2})?)', text)
        if m:
            digits = re.sub(r'[^\d.]', '', m.group(1))
            try:
                return int(float(digits))
            except ValueError:
                pass
        return 0
