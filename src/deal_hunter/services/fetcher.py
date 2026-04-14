"""Deal fetching and deduplication."""

import logging
import re
from datetime import datetime
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Any

from deal_hunter.sources.base import Deal

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from deal_hunter.storage.models import Offer

logger = logging.getLogger(__name__)


def _dto_to_payload(dto: Deal) -> dict:
    """Serialize a fetch DTO into a JSON-safe payload dict for history storage."""
    return {
        "id": dto.id,
        "title": dto.title,
        "price": dto.price,
        "link": dto.link,
        "source": dto.source,
        "description": dto.description,
        "temperature": dto.temperature,
        "image_url": dto.image_url,
        "published_at": dto.published_at,
    }


class DealFetcher:
    """Fetches deals from configured sources and deduplicates."""

    def __init__(
        self,
        source_registry: dict[str, Any] | None = None,
        *,
        profile_name: str = "",
    ) -> None:
        self.source_registry = source_registry or {}
        self.profile_name = profile_name

    def ingest_one(
        self,
        session: "Session",
        dto: Deal,
        profile: dict,
        *,
        score: int = 0,
        category: str = "",
    ) -> "Offer":
        """Upsert one DTO, append payload history, emit appropriate DealEvent.

        Returns the upserted Offer ORM instance.
        """
        from deal_hunter.storage.models import Offer
        from deal_hunter.storage.repositories import (
            DealEventRepository,
            OfferPayloadHistoryRepository,
            OfferRepository,
        )

        repo = OfferRepository(session)
        payloads = OfferPayloadHistoryRepository(session)
        events = DealEventRepository(session)

        existing = session.get(Offer, dto.id)
        old_price = existing.current_price_pln if existing else None
        old_availability = existing.availability if existing else None

        effective_score = score or getattr(dto, "score", 0) or 0
        effective_category = category or profile.get("category", "")

        offer = repo.upsert(
            id=dto.id,
            raw_title=dto.title,
            current_price_pln=dto.price,
            url=dto.link,
            source=dto.source,
            description=dto.description,
            image_url=dto.image_url,
            profile=self.profile_name,
            score=effective_score,
            category=effective_category,
            first_seen_at="",
            last_seen_at="",
        )

        captured_at = datetime.now().isoformat()
        payloads.append(
            offer_id=offer.id,
            raw_payload=_dto_to_payload(dto),
            captured_at=captured_at,
        )

        if existing is None:
            events.emit(
                offer_id=offer.id,
                event_type="new_listing",
                price_at_event=offer.current_price_pln,
                payload={"first_price": offer.current_price_pln},
                created_at=captured_at,
            )
        else:
            new_price = offer.current_price_pln
            if old_price and new_price and new_price < old_price:
                events.emit(
                    offer_id=offer.id,
                    event_type="price_drop",
                    price_at_event=new_price,
                    payload={
                        "old_price": old_price,
                        "new_price": new_price,
                        "diff_pln": old_price - new_price,
                    },
                    created_at=captured_at,
                )
            elif old_price and new_price and new_price > old_price:
                events.emit(
                    offer_id=offer.id,
                    event_type="price_increase",
                    price_at_event=new_price,
                    payload={
                        "old_price": old_price,
                        "new_price": new_price,
                        "diff_pln": new_price - old_price,
                    },
                    created_at=captured_at,
                )
            if old_availability == "out_of_stock" and offer.availability == "in_stock":
                events.emit(
                    offer_id=offer.id,
                    event_type="back_in_stock",
                    price_at_event=new_price,
                    created_at=captured_at,
                )

        return offer

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
