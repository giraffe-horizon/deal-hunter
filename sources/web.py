"""Generic web scraper source — configurable via YAML selectors."""

import re
import logging
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import Source, Deal

logger = logging.getLogger(__name__)


class WebSource(Source):
    """Generic web scraper that uses CSS selectors from profile config.

    Config format in profile YAML:
        sources:
          web:
            sites:
              - url: "https://example.com/deals"
                base_url: "https://example.com"
                selectors:
                  container: "div.product"
                  title: "h2.name"
                  price: "span.price"
                  link: "a@href"
                  image: "img@src"
    """

    def fetch_deals(self, config: dict) -> list[Deal]:
        """Fetch deals from all configured sites."""
        sites = config.get("sites", [])
        all_deals = []

        for site in sites:
            try:
                deals = self._scrape_site(site)
                all_deals.extend(deals)
            except Exception as e:
                logger.error(f"WebSource: failed to scrape {site.get('url', '?')}: {e}",
                             exc_info=True)

        return all_deals

    def _scrape_site(self, site: dict) -> list[Deal]:
        """Scrape a single site using configured selectors."""
        url = site.get("url", "")
        if not url:
            logger.warning("WebSource: site has no URL, skipping")
            return []

        selectors = site.get("selectors", {})
        base_url = site.get("base_url", url)

        html = self._fetch_page(url)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")

        container_sel = selectors.get("container", "")
        if not container_sel:
            logger.warning(f"WebSource: no container selector for {url}")
            return []

        containers = soup.select(container_sel)
        logger.info(f"WebSource: found {len(containers)} containers on {url}")

        deals = []
        for i, container in enumerate(containers):
            try:
                title = self._extract(container, selectors.get("title", ""))
                price_text = self._extract(container, selectors.get("price", ""))
                link = self._extract(container, selectors.get("link", ""))
                image = self._extract(container, selectors.get("image", ""))

                if not title or not price_text:
                    continue

                price = self._parse_price(price_text)
                if price is None:
                    continue

                # Resolve relative URLs
                if link and not link.startswith("http"):
                    link = urljoin(base_url, link)
                if image and not image.startswith("http"):
                    image = urljoin(base_url, image)

                deal = Deal(
                    id=f"web:{url}:{i}",
                    title=title.strip(),
                    price=price,
                    link=link or url,
                    source="web",
                    description="",
                    temperature=0,
                    image_url=image or "",
                    published_at="",
                )
                deals.append(deal)
            except Exception as e:
                logger.debug(f"WebSource: skipping container {i} on {url}: {e}")

        return deals

    @staticmethod
    def _extract(container, selector: str) -> str:
        """Extract text or attribute from a container using selector.

        Supports @attr syntax: "a@href" finds <a> then gets href attribute.
        Without @attr: gets text content.
        """
        if not selector:
            return ""

        # Parse @attr syntax
        if "@" in selector:
            parts = selector.split("@", 1)
            css_sel = parts[0].strip()
            attr = parts[1].strip()
            el = container.select_one(css_sel) if css_sel else container
            if el:
                return el.get(attr, "")
            return ""

        el = container.select_one(selector)
        if el:
            return el.get_text(strip=True)
        return ""

    @staticmethod
    def _parse_price(text: str) -> int | None:
        """Extract numeric price from text. Returns int or None."""
        # Remove spaces, non-breaking spaces
        cleaned = text.replace('\xa0', '').replace(' ', '')
        # Match number with optional decimal (comma or dot)
        match = re.search(r'(\d[\d\s]*[\d]?)[,.]?\d{0,2}', cleaned)
        if match:
            digits = re.sub(r'\D', '', match.group(0).split(',')[0].split('.')[0])
            if digits:
                return int(digits)
        return None
