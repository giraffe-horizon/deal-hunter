"""Centrumrowerowe.pl source — bike shop scraper."""

import json
import logging
import re

from bs4 import BeautifulSoup

from .base import Deal, Source

logger = logging.getLogger(__name__)


class CentrumroweroweSource(Source):
    """Scrapes product listings from Centrumrowerowe.pl."""

    SOURCE_NAME = "centrumrowerowe"
    BASE_URL = "https://centrumrowerowe.pl"

    def fetch_deals(self, config: dict) -> list[Deal]:
        urls: list[str] = config.get("urls", [])
        if not urls:
            logger.warning("Centrumrowerowe: no urls configured")
            return []

        all_deals: list[Deal] = []
        for url in urls:
            html_text = self._fetch_page(url)
            if html_text:
                deals = self._parse_page(html_text, url)
                all_deals.extend(deals)
                logger.info(f"Centrumrowerowe: parsed {len(deals)} deals from {url}")
            else:
                logger.error(f"Centrumrowerowe: failed to fetch {url}")

        return all_deals

    def _parse_page(self, html_text: str, url: str) -> list[Deal]:
        # Strategy 1: JSON-LD ItemList
        deals = self._parse_jsonld(html_text, url)
        if deals:
            return deals
        # Strategy 2: dataLayer input fields
        deals = self._parse_datalayer_inputs(html_text, url)
        if deals:
            return deals
        # Strategy 3: HTML product cards
        return self._parse_html(html_text, url)

    def _parse_jsonld(self, html_text: str, url: str) -> list[Deal]:
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
                logger.debug(f"Centrumrowerowe JSON-LD parse error: {e}")
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

            return Deal(
                id=f"centrumrowerowe:{native_id}",
                title=name,
                price=price,
                link=link,
                source=self.SOURCE_NAME,
                description=f"Centrumrowerowe: {url}",
                temperature=0,
                image_url=image_url,
                published_at="",
                regular_price=regular_price,
            )
        except Exception as e:
            logger.debug(f"Centrumrowerowe JSON-LD deal error: {e}")
            return None

    def _parse_datalayer_inputs(self, html_text: str, url: str) -> list[Deal]:
        """Parse input[name=dataLayerItem] hidden fields."""
        soup = BeautifulSoup(html_text, "html.parser")
        deals: list[Deal] = []

        inputs = soup.find_all("input", attrs={"name": "dataLayerItem"})
        for inp in inputs:
            try:
                raw = inp.get("value", "")
                if not raw:
                    continue
                data = json.loads(raw)
                deal = self._datalayer_to_deal(data, url)
                if deal:
                    deals.append(deal)
            except (json.JSONDecodeError, TypeError) as e:
                logger.debug(f"Centrumrowerowe dataLayer parse error: {e}")
                continue

        return deals

    def _datalayer_to_deal(self, data: dict, url: str) -> Deal | None:
        try:
            name = data.get("name", "").strip()
            if not name:
                return None

            native_id = str(data.get("id", data.get("sku", re.sub(r"\W+", "_", name[:60]))))
            price = int(float(data.get("price", 0)))

            link = data.get("url", url)
            if not link.startswith("http"):
                link = f"{self.BASE_URL}{link}"

            category = data.get("category", "")
            brand = data.get("brand", "")
            desc_parts = [p for p in [brand, category] if p]
            description = " | ".join(desc_parts) if desc_parts else f"Centrumrowerowe: {url}"

            return Deal(
                id=f"centrumrowerowe:{native_id}",
                title=name,
                price=price,
                link=link,
                source=self.SOURCE_NAME,
                description=description,
                temperature=0,
                image_url="",
                published_at="",
            )
        except Exception as e:
            logger.debug(f"Centrumrowerowe dataLayer deal error: {e}")
            return None

    def _parse_html(self, html_text: str, url: str) -> list[Deal]:
        """Fallback: parse HTML product cards."""
        soup = BeautifulSoup(html_text, "html.parser")
        deals: list[Deal] = []

        products = soup.find_all(
            "div", class_=re.compile(r"product-item|product-card|product-miniature")
        )
        if not products:
            products = soup.find_all("article", class_=re.compile(r"product"))

        for prod in products:
            deal = self._parse_html_product(prod, url)
            if deal:
                deals.append(deal)

        return deals

    def _parse_html_product(self, prod, url: str) -> Deal | None:
        try:
            title_tag = prod.find(class_=re.compile(r"product-title|product-name|name"))
            if not title_tag:
                title_tag = prod.find(["h2", "h3", "h4"])
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

            price = 0
            price_tag = prod.find(class_=re.compile(r"price"))
            if price_tag:
                price = self.extract_price(price_tag.get_text())

            image_url = ""
            img = prod.find("img")
            if img:
                image_url = img.get("src", "") or img.get("data-src", "")
                if image_url and not image_url.startswith("http"):
                    image_url = f"{self.BASE_URL}{image_url}"

            native_id = re.sub(r"\W+", "_", title[:60])

            return Deal(
                id=f"centrumrowerowe:{native_id}",
                title=title,
                price=price,
                link=link,
                source=self.SOURCE_NAME,
                description=f"Centrumrowerowe: {url}",
                temperature=0,
                image_url=image_url,
                published_at="",
            )
        except Exception as e:
            logger.debug(f"Centrumrowerowe HTML parse error: {e}")
            return None

