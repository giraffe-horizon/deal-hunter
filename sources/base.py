"""Base classes for deal sources."""

import logging
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import requests

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.5",
}

MAX_RETRIES = 3
RETRY_DELAY = 3
MIN_REQUEST_INTERVAL = 2.0


@dataclass
class Deal:
    """Normalized deal from any source."""

    id: str  # unique: f"{source}:{native_id}"
    title: str
    price: int  # in PLN, 0 if unknown
    link: str
    source: str  # "pepper", "ceneo", "proshop", "web"
    description: str
    temperature: int  # Pepper only, rest 0
    image_url: str
    published_at: str  # ISO datetime or ""
    regular_price: int = 0  # original/regular price before discount
    alt_links: list[dict] = field(default_factory=list)  # [{"source": "...", "link": "...", "price": N}]

    def __post_init__(self):
        if not self.title or not self.title.strip():
            raise ValueError(f"Deal has empty title: {self.id}")
        if self.price < 0:
            self.price = 0
        self.temperature = self.temperature or 0


class Source(ABC):
    """Base class for deal sources with rate limiting and retry."""

    def __init__(self) -> None:
        self._last_request_time = 0.0

    def _rate_limit(self) -> None:
        """Enforce minimum interval between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.time()

    def _fetch_page(self, url: str) -> str | None:
        """Fetch a page with retry and rate limiting."""
        self._rate_limit()
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = requests.get(url, headers=HEADERS, timeout=15)
                resp.raise_for_status()
                return resp.text
            except Exception as e:
                logger.warning(f"Attempt {attempt}/{MAX_RETRIES} failed for {url}: {e}")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * attempt)
        return None

    @staticmethod
    def extract_price(text: str) -> int:
        """Extract integer price from text, handling European number formats.

        Handles: '1 234 PLN', '1.234,50 zł', '18.999 ZŁ', '1234',
                 '1 234,50', '299,99 €'.
        """
        if not text:
            return 0
        # Remove everything except digits, dots, commas
        cleaned = re.sub(r"[^\d.,]", "", text.replace("\xa0", "").replace(" ", ""))
        if not cleaned:
            return 0

        # Comma as decimal separator (European format): "1.234,50" or "1234,50"
        if "," in cleaned:
            m = re.match(r"^([\d.]+),(\d{1,2})$", cleaned)
            if m:
                integer_part = m.group(1).replace(".", "")
                return int(integer_part) if integer_part else 0
            # Comma followed by 3+ digits = thousands separator
            cleaned = cleaned.replace(",", "")

        # Dot followed by groups of 3 digits = thousands separator: "18.999"
        if "." in cleaned:
            if re.match(r"^\d{1,3}(?:\.\d{3})+$", cleaned):
                return int(cleaned.replace(".", ""))
            # Otherwise dot is decimal separator
            try:
                return int(float(cleaned))
            except ValueError:
                pass

        # Pure digits
        digits = re.sub(r"\D", "", cleaned)
        return int(digits) if digits else 0

    @abstractmethod
    def fetch_deals(self, config: dict) -> list[Deal]:
        """Fetch deals from this source. Config comes from profile YAML."""
        pass
