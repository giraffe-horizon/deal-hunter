"""Veloshop.pl source — OpenCart bike shop scraper."""

import logging
import re

from bs4 import BeautifulSoup

from .base import Deal, Source

logger = logging.getLogger(__name__)


class VeloshopSource(Source):
    """Scrapes product listings from Veloshop.pl (OpenCart)."""

    SOURCE_NAME = "veloshop"
    BASE_URL = "https://veloshop.pl"

    def fetch_deals(self, config: dict) -> list[Deal]:
        urls: list[str] = config.get("urls", [])
        if not urls:
            logger.warning("Veloshop: no urls configured")
            return []

        all_deals: list[Deal] = []
        for url in urls:
            html_text = self._fetch_page(url)
            if html_text:
                deals = self._parse_page(html_text, url)
                all_deals.extend(deals)
                logger.info(f"Veloshop: parsed {len(deals)} deals from {url}")
            else:
                logger.error(f"Veloshop: failed to fetch {url}")

        return all_deals

    def _parse_page(self, html_text: str, url: str) -> list[Deal]:
        soup = BeautifulSoup(html_text, "html.parser")
        deals: list[Deal] = []

        products = soup.select("div.product-thumb, .product-layout, .product-grid .product-item")
        if not products:
            products = soup.find_all("div", class_=re.compile(r"product-thumb|product-layout"))

        for prod in products:
            deal = self._parse_product(prod, url)
            if deal:
                deals.append(deal)

        return deals

    def _parse_product(self, prod, url: str) -> Deal | None:
        try:
            # Title — OpenCart uses h4.product-title or .caption h4
            title_tag = prod.select_one("h4.product-title > a, .caption h4 a, h4 a")
            if not title_tag:
                title_tag = prod.find(["h3", "h4", "h5"])
                if title_tag:
                    link_inner = title_tag.find("a")
                    if link_inner:
                        title_tag = link_inner
            if not title_tag:
                return None

            title = title_tag.get_text().strip()
            if not title:
                return None

            href = title_tag.get("href", "")
            link = href if href.startswith("http") else f"{self.BASE_URL}{href}" if href else url

            # Price — OpenCart: span.price-new for sale, span.price-old for regular
            price = 0
            regular_price = 0

            price_new = prod.find("span", class_="price-new")
            price_old = prod.find("span", class_="price-old")

            if price_new:
                price = self._extract_price(price_new.get_text())
            if price_old:
                regular_price = self._extract_price(price_old.get_text())

            # If no sale price, look for any price
            if not price:
                price_tag = prod.find(class_=re.compile(r"price"))
                if price_tag:
                    price = self._extract_price(price_tag.get_text())

            # Image
            image_url = ""
            img = prod.find("img")
            if img:
                image_url = img.get("src", "") or img.get("data-src", "")
                if image_url and not image_url.startswith("http"):
                    image_url = f"{self.BASE_URL}{image_url}"

            # Extract size from URL slug (e.g., '-51cm-', '-56cm-')
            size_info = ""
            slug_match = re.search(r"-(\d{2})cm-", href)
            if slug_match:
                size_info = f"{slug_match.group(1)}cm"

            # Also check title for size
            if not size_info:
                title_size = re.search(r"\b(\d{2})\s*cm\b", title, re.IGNORECASE)
                if title_size:
                    size_info = f"{title_size.group(1)}cm"

            description = f"Size: {size_info}" if size_info else f"Veloshop: {url}"

            # ID from href or title
            native_id = ""
            if href:
                m = re.search(r"product_id=(\d+)", href)
                if m:
                    native_id = m.group(1)
                else:
                    m = re.search(r"/(\d+)[-.]", href)
                    native_id = m.group(1) if m else ""
            if not native_id:
                native_id = re.sub(r"\W+", "_", title[:60])

            return Deal(
                id=f"veloshop:{native_id}",
                title=title,
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
            logger.debug(f"Veloshop parse error: {e}")
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
