"""Deal fetching and deduplication."""

import logging
import re
from difflib import SequenceMatcher
from typing import Any

from sources.base import Deal

logger = logging.getLogger(__name__)


class DealFetcher:
    """Fetches deals from configured sources and deduplicates."""

    def __init__(self, source_registry: dict[str, Any]) -> None:
        self.source_registry = source_registry

    def fetch_all(self, profile: dict) -> tuple[list[Deal], dict[str, bool], list[str]]:
        """Fetch deals from all configured sources.

        Returns (deals, source_results, errors).
        """
        sources_config = profile.get("sources", {})
        all_deals: list[Deal] = []
        source_results: dict[str, bool] = {}
        errors: list[str] = []

        for source_name, source_config in sources_config.items():
            source_class = self.source_registry.get(source_name)
            if not source_class:
                logger.warning(f"Unknown source: {source_name}")
                continue

            try:
                source = source_class()
                deals = source.fetch_deals(source_config)
                all_deals.extend(deals)
                source_results[source_name] = True
                logger.info(f"Source {source_name}: {len(deals)} deals fetched")
            except Exception as e:
                logger.error(f"Source {source_name} failed: {e}", exc_info=True)
                source_results[source_name] = False
                errors.append(f"{source_name}: {e}")

        return all_deals, source_results, errors

    def deduplicate(self, deals: list[Deal], dedup_config: dict | None = None) -> list[Deal]:
        """Deduplicate by ID, then merge cross-source duplicates by fuzzy title + price."""
        config = dedup_config or {}
        enabled = config.get("enabled", True)
        price_tolerance = config.get("price_tolerance", 0.05)
        title_similarity = config.get("title_similarity", 0.85)

        seen_ids: set[str] = set()
        unique: list[Deal] = []
        seen_keys: list[tuple[str, int, int]] = []

        for d in deals:
            if d.id in seen_ids:
                continue
            seen_ids.add(d.id)

            norm_title = self._normalize_title(d.title)[:60]

            if not enabled:
                unique.append(d)
                continue

            merged = False
            for _i, (existing_title, existing_price, unique_idx) in enumerate(seen_keys):
                if d.price > 0 and (norm_title, d.price) == (existing_title, existing_price):
                    unique[unique_idx].alt_links.append(
                        {"source": d.source, "link": d.link, "price": d.price}
                    )
                    merged = True
                    break

                if d.price > 0 and existing_price > 0:
                    price_diff = abs(d.price - existing_price) / max(d.price, existing_price)
                    if price_diff <= price_tolerance:
                        ratio = SequenceMatcher(None, existing_title, norm_title).ratio()
                        if ratio >= title_similarity:
                            unique[unique_idx].alt_links.append(
                                {"source": d.source, "link": d.link, "price": d.price}
                            )
                            merged = True
                            break

            if not merged:
                seen_keys.append((norm_title, d.price, len(unique)))
                unique.append(d)

        return unique

    @staticmethod
    def _normalize_title(title: str) -> str:
        """Normalize title for dedup: lowercase, strip, alphanumeric only."""
        text = title.lower().strip()
        text = re.sub(r"[^\w\s]", "", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()
