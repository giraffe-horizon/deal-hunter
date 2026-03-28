"""Rowertour.com source — bike shop scraper."""

import json
import logging
import re

from bs4 import BeautifulSoup

from .base import Deal, Source

logger = logging.getLogger(__name__)


class RowertourSource(Source):
    """Scrapes product listings from Rowertour.com."""

    SOURCE_NAME = "rowertour"
    BASE_URL = "https://www.rowertour.com"

    def fetch_deals(self, config: dict) -> list[Deal]:
        urls: list[str] = config.get("urls", [])
        if not urls:
            logger.warning("Rowertour: no urls configured")
            return []

        all_deals: list[Deal] = []
        for url in urls:
            html_text = self._fetch_page(url)
            if html_text:
                deals = self._parse_page(html_text, url)
                all_deals.extend(deals)
                logger.info(f"Rowertour: parsed {len(deals)} deals from {url}")
            else:
                logger.error(f"Rowertour: failed to fetch {url}")

        return all_deals

    def _parse_page(self, html_text: str, url: str) -> list[Deal]:
        deals = self._parse_html(html_text, url)
        if deals:
            return deals
        return self._parse_jsonld(html_text, url)

    def _parse_html(self, html_text: str, url: str) -> list[Deal]:
        soup = BeautifulSoup(html_text, "html.parser")
        deals: list[Deal] = []

        products = soup.select(
            ".box_item_wrapper, article.product-miniature, "
            "div.product-container, .product-item, .product-card"
        )
        if not products:
            products = soup.find_all("div", class_=re.compile(r"product"))

        for prod in products:
            deal = self._parse_product(prod, url)
            if deal:
                deals.append(deal)

        return deals

    def _parse_product(self, prod, url: str) -> Deal | None:
        try:
            # Title
            title_tag = prod.find(
                class_=re.compile(r"product-title|product-name|box_item_name|name")
            )
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
                class_=re.compile(r"product-price|price-new|price-current|current-price|price")
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
                image_url = (
                    img.get("data-src", "") or img.get("src", "") or img.get("data-original", "")
                )
                if image_url and not image_url.startswith("http"):
                    image_url = f"{self.BASE_URL}{image_url}"

            # ID
            native_id = prod.get("data-id", "") or prod.get("data-id-product", "")
            if not native_id and href:
                m = re.search(r"/(\d+)[-.]", href)
                native_id = m.group(1) if m else ""
            if not native_id:
                native_id = re.sub(r"\W+", "_", title[:60])

            return Deal(
                id=f"rowertour:{native_id}",
                title=title,
                price=price,
                link=link,
                source=self.SOURCE_NAME,
                description=f"Rowertour: {url}",
                temperature=0,
                image_url=image_url,
                published_at="",
                regular_price=regular_price,
            )
        except Exception as e:
            logger.debug(f"Rowertour parse error: {e}")
            return None

    def _parse_jsonld(self, html_text: str, url: str) -> list[Deal]:
        """Fallback: parse JSON-LD ItemList."""
        soup = BeautifulSoup(html_text, "html.parser")
        deals: list[Deal] = []

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                if isinstance(data, list):
                    for item in data:
                        if item.get("@type") == "ItemList":
                            data = item
                            break
                    else:
                        continue

                if data.get("@type") != "ItemList":
                    continue

                for item in data.get("itemListElement", []):
                    product = item.get("item", item)
                    deal = self._jsonld_to_deal(product, url)
                    if deal:
                        deals.append(deal)
            except (json.JSONDecodeError, TypeError, KeyError) as e:
                logger.debug(f"Rowertour JSON-LD parse error: {e}")
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
                m = re.search(r"/(\d+)[-.]", link)
                native_id = m.group(1) if m else re.sub(r"\W+", "_", name[:60])

            return Deal(
                id=f"rowertour:{native_id}",
                title=name,
                price=price,
                link=link,
                source=self.SOURCE_NAME,
                description=f"Rowertour: {url}",
                temperature=0,
                image_url=image_url,
                published_at="",
                regular_price=regular_price,
            )
        except Exception as e:
            logger.debug(f"Rowertour JSON-LD deal error: {e}")
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
