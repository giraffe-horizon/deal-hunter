"""Canyon.com PL source — outlet and catalog scraper."""

import html
import json
import logging
import re

from bs4 import BeautifulSoup

from .base import Deal, Source

logger = logging.getLogger(__name__)


class CanyonSource(Source):
    """Scrapes product listings from Canyon.com PL outlet/catalog pages."""

    SOURCE_NAME = "canyon"

    def fetch_deals(self, config: dict) -> list[Deal]:
        urls: list[str] = config.get("urls", [])
        if not urls:
            logger.warning("Canyon: no urls configured")
            return []

        all_deals: list[Deal] = []
        for url in urls:
            html_text = self._fetch_page(url)
            if html_text:
                deals = self._parse_page(html_text, url)
                all_deals.extend(deals)
                logger.info(f"Canyon: parsed {len(deals)} deals from {url}")
            else:
                logger.error(f"Canyon: failed to fetch {url}")

        return all_deals

    def _parse_page(self, html_text: str, url: str) -> list[Deal]:
        deals = self._parse_gtm_impressions(html_text, url)
        if deals:
            return deals
        return self._parse_product_grid(html_text, url)

    def _parse_gtm_impressions(self, html_text: str, url: str) -> list[Deal]:
        """Parse data-gtm-impression JSON attributes."""
        soup = BeautifulSoup(html_text, "html.parser")
        deals: list[Deal] = []

        elements = soup.find_all(attrs={"data-gtm-impression": True})
        for el in elements:
            try:
                raw = html.unescape(el.get("data-gtm-impression", ""))
                data = json.loads(raw)
                deal = self._gtm_to_deal(data, el, url)
                if deal:
                    deals.append(deal)
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.debug(f"Canyon GTM parse error: {e}")
                continue

        return deals

    def _gtm_to_deal(self, data: dict, el, url: str) -> Deal | None:
        """Convert a GTM impression JSON object to a Deal."""
        try:
            name = data.get("name", "").strip()
            if not name:
                return None

            native_id = str(data.get("id", data.get("sku", name[:50])))
            price = int(float(data.get("price", 0)))

            # Regular price and discount
            regular_price = 0
            discount = data.get("discount", data.get("metric4", 0))
            if discount and price:
                try:
                    regular_price = price + int(float(discount))
                except (ValueError, TypeError):
                    pass

            # Color/variant from GTM data
            variant = data.get("variant", "")
            dimension = data.get("dimension54", data.get("dimension50", ""))
            color = variant or dimension

            # Build description with available size info
            desc_parts = []
            if color:
                desc_parts.append(f"Color: {color}")
            category = data.get("category", "")
            if category:
                desc_parts.append(category)

            # Extract sizes from surrounding HTML
            sizes = self._extract_sizes(el)
            if sizes:
                desc_parts.append(f"Sizes: {sizes}")

            description = " | ".join(desc_parts) if desc_parts else f"Canyon: {url}"

            # Link
            link_tag = el.find("a", href=True)
            link = ""
            if link_tag:
                href = link_tag.get("href", "")
                link = href if href.startswith("http") else f"https://www.canyon.com{href}"
            if not link:
                link = url

            # Image
            image_url = ""
            img = el.find("img")
            if img:
                image_url = img.get("src", "") or img.get("data-src", "")
                if image_url and not image_url.startswith("http"):
                    image_url = f"https://www.canyon.com{image_url}"

            return Deal(
                id=f"canyon:{native_id}",
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
            logger.debug(f"Canyon GTM deal error: {e}")
            return None

    def _parse_product_grid(self, html_text: str, url: str) -> list[Deal]:
        """Fallback: parse productGrid HTML tiles."""
        soup = BeautifulSoup(html_text, "html.parser")
        deals: list[Deal] = []

        tiles = soup.select(
            ".productGrid__product, .productTile, "
            ".product-tile, .js-productTile"
        )
        if not tiles:
            tiles = soup.find_all("div", class_=re.compile(r"product.*tile|product.*card"))

        for tile in tiles:
            deal = self._parse_tile(tile, url)
            if deal:
                deals.append(deal)

        return deals

    def _parse_tile(self, tile, url: str) -> Deal | None:
        try:
            title_tag = tile.find(
                class_=re.compile(r"productTile__productName|product.*name|product.*title")
            )
            if not title_tag:
                title_tag = tile.find(["h2", "h3", "h4"])
            if not title_tag:
                return None

            title = title_tag.get_text().strip()
            if not title:
                return None

            link = ""
            link_tag = tile.find("a", href=True)
            if link_tag:
                href = link_tag.get("href", "")
                link = href if href.startswith("http") else f"https://www.canyon.com{href}"

            price = 0
            regular_price = 0
            sale_tag = tile.find(
                class_=re.compile(r"productTile__productSalePrice|price.*sale|price.*current")
            )
            if sale_tag:
                price = self.extract_price(sale_tag.get_text())
            old_tag = tile.find(
                class_=re.compile(r"productTile__productOldPrice|price.*old|price.*original")
            )
            if old_tag:
                regular_price = self.extract_price(old_tag.get_text())
            if not price:
                price_tag = tile.find(class_=re.compile(r"price"))
                if price_tag:
                    price = self.extract_price(price_tag.get_text())

            image_url = ""
            img = tile.find("img")
            if img:
                image_url = img.get("src", "") or img.get("data-src", "")
                if image_url and not image_url.startswith("http"):
                    image_url = f"https://www.canyon.com{image_url}"

            native_id = re.sub(r"\W+", "_", title[:60])

            sizes = self._extract_sizes(tile)
            description = f"Sizes: {sizes}" if sizes else f"Canyon: {url}"

            return Deal(
                id=f"canyon:{native_id}",
                title=title,
                price=price,
                link=link or url,
                source=self.SOURCE_NAME,
                description=description,
                temperature=0,
                image_url=image_url,
                published_at="",
                regular_price=regular_price,
            )
        except Exception as e:
            logger.debug(f"Canyon tile parse error: {e}")
            return None

    @staticmethod
    def _extract_sizes(element) -> str:
        """Extract available sizes from element text."""
        text = element.get_text()
        m = re.search(r"[Dd]ostępn[ey]\s+(?:tylko\s+)?w\s+(.+?)(?:\.|$)", text)
        if m:
            return m.group(1).strip()
        size_tags = element.find_all(class_=re.compile(r"size"))
        if size_tags:
            sizes = [s.get_text().strip() for s in size_tags if s.get_text().strip()]
            if sizes:
                return " | ".join(sizes)
        return ""

