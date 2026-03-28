"""Pepper.pl source — scrapes deals with Vue3 JSON + HTML fallback."""

import json
import logging
import re
from datetime import datetime, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import Deal, Source

logger = logging.getLogger(__name__)


class PepperSource(Source):
    """Scrapes deals from Pepper.pl."""

    SOURCE_NAME = "pepper"

    def fetch_deals(self, config: dict) -> list[Deal]:
        """Fetch deals from configured Pepper URLs.

        Args:
            config: Profile source config with 'urls' key.
        """
        urls: list[str] = config.get("urls", [])
        if not urls:
            logger.warning("Pepper: no URLs configured")
            return []

        all_deals: list[Deal] = []
        for url in urls:
            html = self._fetch_page(url)
            if html:
                deals = self._parse_deals(html, url)
                all_deals.extend(deals)
                logger.info(f"Pepper: parsed {len(deals)} deals from {url}")
            else:
                logger.error(f"Pepper: failed to fetch {url}")

        return all_deals

    def _parse_deals(self, html: str, base_url: str = "https://www.pepper.pl") -> list[Deal]:
        """Parse deals from Pepper HTML."""
        soup = BeautifulSoup(html, "html.parser")
        deals: list[Deal] = []
        articles = soup.find_all("article", class_=re.compile(r"thread"))

        for art in articles:
            deal = self._parse_vue3(art) or self._parse_html(art, base_url)
            if deal:
                deals.append(deal)
        return deals

    def _parse_vue3(self, art) -> Deal | None:
        """Try to extract data from Vue3 data attribute."""
        vue_div = art.find("div", class_="js-vue3")
        if not vue_div or not vue_div.get("data-vue3"):
            return None
        try:
            data = json.loads(vue_div["data-vue3"])
            thread = data.get("props", {}).get("thread", {})
            title = thread.get("title", "")
            slug = thread.get("titleSlug", "")
            tid = thread.get("threadId", "")
            link = f"https://www.pepper.pl/promocje/{slug}-{tid}" if slug and tid else ""

            # Filter expired deals
            if thread.get("isExpired") or thread.get("status") in (
                "expired",
                "wygas\u0142a",
                "hidden",
            ):
                return None

            price = 0
            price_obj = thread.get("price")
            if price_obj:
                if isinstance(price_obj, dict):
                    price = int(float(price_obj.get("amount", 0)))
                else:
                    price = Source.extract_price(str(price_obj))

            # Regular/next best price
            regular_price = 0
            for key in ("nextBestPrice", "regularPrice", "originalPrice"):
                rp = thread.get(key)
                if rp:
                    if isinstance(rp, dict):
                        regular_price = int(float(rp.get("amount", 0)))
                    else:
                        regular_price = Source.extract_price(str(rp))
                    if regular_price > 0:
                        break
            if regular_price == 0:
                merchant = thread.get("merchant")
                if isinstance(merchant, dict) and merchant.get("price"):
                    mp = merchant["price"]
                    if isinstance(mp, dict):
                        regular_price = int(float(mp.get("amount", 0)))
                    else:
                        regular_price = Source.extract_price(str(mp))

            desc = thread.get("description", "")
            temperature = thread.get("temperature", 0)

            # Image URL
            image_url = ""
            image_data = thread.get("mainImage") or thread.get("image")
            if isinstance(image_data, dict):
                image_url = image_data.get("url", "") or image_data.get("path", "")
            elif isinstance(image_data, str):
                image_url = image_data

            # Publication date
            published_at = thread.get("publishedAt") or thread.get("createdAt") or ""
            if published_at:
                try:
                    pub_dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                    if datetime.now().astimezone() - pub_dt > timedelta(days=30):
                        return None
                except Exception:
                    pass

            native_id = str(tid) if tid else link
            return Deal(
                id=f"pepper:{native_id}",
                title=title,
                price=price,
                link=link,
                source=self.SOURCE_NAME,
                description=desc,
                temperature=temperature,
                image_url=image_url,
                published_at=published_at if published_at else "",
                regular_price=regular_price,
            )
        except Exception as e:
            logger.debug(f"Pepper Vue3 parse error: {e}")
            return None

    def _parse_html(self, art, base_url: str) -> Deal | None:
        """Fallback — parse deal from HTML tags."""
        art_classes = " ".join(art.get("class", []))
        if re.search(r"thread--expired|thread--hide|expired", art_classes):
            return None

        title_tag = art.find("a", class_=re.compile(r"thread-title"))
        if not title_tag:
            return None

        title = title_tag.get_text().strip()
        link = title_tag.get("href", "")
        if link and not link.startswith("http"):
            link = urljoin(base_url, link)

        price = 0
        price_tag = art.find("span", class_=re.compile(r"thread-price"))
        if price_tag:
            price = Source.extract_price(price_tag.get_text())

        # Regular price from strikethrough/muted text
        regular_price = 0
        old_price_tag = art.find(
            "span", class_=re.compile(r"mute--text|text--lineThrough|overflow--fade")
        )
        if old_price_tag:
            regular_price = Source.extract_price(old_price_tag.get_text())

        desc = ""
        desc_tag = art.find("div", class_=re.compile(r"description|excerpt"))
        if desc_tag:
            desc = desc_tag.get_text().strip()

        temp = 0
        temp_tag = art.find("span", class_=re.compile(r"vote-temp"))
        if temp_tag:
            try:
                temp = int(re.sub(r"[^\d-]", "", temp_tag.get_text()) or 0)
            except ValueError:
                temp = 0

        # Image
        image_url = ""
        img_tag = art.find("img")
        if img_tag:
            image_url = img_tag.get("src", "") or img_tag.get("data-src", "")

        # Publication date
        published_at = ""
        time_tag = art.find("time")
        if time_tag and time_tag.get("datetime"):
            raw_dt = time_tag["datetime"]
            try:
                pub_dt = datetime.fromisoformat(raw_dt.replace("Z", "+00:00"))
                if datetime.now().astimezone() - pub_dt > timedelta(days=30):
                    return None
                published_at = raw_dt
            except Exception:
                pass

        native_id = link or title
        return Deal(
            id=f"pepper:{native_id}",
            title=title,
            price=price,
            link=link,
            source=self.SOURCE_NAME,
            description=desc,
            temperature=temp,
            image_url=image_url,
            published_at=published_at,
            regular_price=regular_price,
        )


