"""RSS/Atom feed source for deal monitoring."""

import hashlib
import logging
import re
import xml.etree.ElementTree as ET

from .base import Deal, Source

logger = logging.getLogger(__name__)

ATOM_NS = "http://www.w3.org/2005/Atom"

# Matches a price-like token: digits with optional space/dot/comma separators
# followed by an optional currency symbol (zł, PLN, EUR, €, $, etc.)
_PRICE_PATTERN = re.compile(
    r"\b(\d[\d\s.,]*\d|\d)\s*(?:zł|PLN|EUR|€|\$|USD|GBP|£)\b",
    re.IGNORECASE,
)


class RssSource(Source):
    """Generic RSS/Atom feed source. Parses standard feeds into Deal objects."""

    @staticmethod
    def _find_price(text: str) -> int:
        """Find price in text by first locating a price token (with currency symbol),
        then delegating to extract_price for number parsing.

        Falls back to extract_price on the full text when no currency symbol found.
        """
        m = _PRICE_PATTERN.search(text)
        if m:
            return Source.extract_price(m.group(0))
        return Source.extract_price(text)

    def fetch_deals(self, config: dict) -> list[Deal]:
        """Fetch deals from one or more RSS/Atom feeds."""
        deals: list[Deal] = []
        for feed_cfg in config.get("feeds", []):
            self._rate_limit()
            url = feed_cfg["url"]
            source_name = feed_cfg.get("source_name", "rss")
            content = self._fetch_page(url)
            if content is None:
                logger.warning(f"Failed to fetch RSS feed: {url}")
                continue
            deals.extend(self._parse_feed(content, source_name))
        return deals

    def _parse_feed(self, xml_content: str, source_name: str) -> list[Deal]:
        """Parse RSS 2.0 or Atom feed XML into Deal objects."""
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            logger.warning(f"Failed to parse RSS/Atom XML: {e}")
            return []

        if root.tag == "rss":
            return self._parse_rss2(root, source_name)
        elif root.tag == f"{{{ATOM_NS}}}feed" or root.tag == "feed":
            return self._parse_atom(root, source_name)
        else:
            logger.warning(f"Unknown feed format: root tag is '{root.tag}'")
            return []

    def _parse_rss2(self, root: ET.Element, source_name: str) -> list[Deal]:
        """Parse RSS 2.0 format."""
        deals: list[Deal] = []
        channel = root.find("channel")
        if channel is None:
            return deals

        for item in channel.findall("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            description = (item.findtext("description") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()
            guid = (item.findtext("guid") or link).strip()

            if not title:
                continue

            price = self._find_price(title)
            if price == 0 and description:
                price = self._find_price(description)

            id_hash = hashlib.md5(guid.encode()).hexdigest()[:12]
            deal_id = f"{source_name}:{id_hash}"

            deals.append(
                Deal(
                    id=deal_id,
                    title=title,
                    price=price,
                    link=link,
                    source=source_name,
                    description=description,
                    temperature=0,
                    image_url="",
                    published_at=pub_date,
                )
            )

        return deals

    def _parse_atom(self, root: ET.Element, source_name: str) -> list[Deal]:
        """Parse Atom format."""
        deals: list[Deal] = []
        ns = f"{{{ATOM_NS}}}" if root.tag.startswith("{") else ""

        for entry in root.findall(f"{ns}entry"):
            title = (entry.findtext(f"{ns}title") or "").strip()
            link_el = entry.find(f"{ns}link")
            link = (link_el.get("href") or "") if link_el is not None else ""
            summary = (entry.findtext(f"{ns}summary") or "").strip()
            published = (entry.findtext(f"{ns}published") or "").strip()
            entry_id = (entry.findtext(f"{ns}id") or link).strip()

            if not title:
                continue

            price = self.extract_price(title)
            if price == 0 and summary:
                price = self.extract_price(summary)

            id_hash = hashlib.md5(entry_id.encode()).hexdigest()[:12]
            deal_id = f"{source_name}:{id_hash}"

            deals.append(
                Deal(
                    id=deal_id,
                    title=title,
                    price=price,
                    link=link,
                    source=source_name,
                    description=summary,
                    temperature=0,
                    image_url="",
                    published_at=published,
                )
            )

        return deals
