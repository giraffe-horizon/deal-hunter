"""Business logic for the Deal Hunter dashboard, decoupled from HTTP routing."""

from storage.sqlite import SQLiteStorage

DEALS_PER_PAGE = 50
SCORE_THRESHOLD = 70


class DealService:
    """Encapsulates deal-related business logic."""

    def __init__(self, db: SQLiteStorage) -> None:
        self.db = db

    def get_comparison_data(self, deal_ids: list[str]) -> dict:
        """Batch-fetch deals, price histories, and lowest prices."""
        deal_ids = deal_ids[:5]
        deals = self.db.get_deals_by_ids(deal_ids) if deal_ids else []
        id_list = [d["id"] for d in deals]
        return {
            "deals": deals,
            "price_histories": self.db.get_price_histories_batch(id_list),
            "lowest_prices": self.db.get_lowest_prices_batch(id_list),
        }

    def score_deals_with_profile(self, deals: list[dict], profile_data: dict) -> list[dict]:
        """Score a list of deal dicts using the given profile config."""
        from filters.base import BaseFilter
        from sources.base import Deal

        scorer = BaseFilter(profile_data)
        scored = []
        for d in deals:
            deal_obj = Deal(
                id=d["id"],
                title=d["title"],
                price=d["price"] or 0,
                link=d["link"] or "",
                source=d["source"] or "",
                description=d["description"] or "",
                temperature=0,
                image_url=d["image_url"] or "",
                published_at="",
            )
            result = scorer.score_deal(deal_obj)
            scored.append(
                {
                    **d,
                    "new_score": result.score,
                    "diff": result.score - (d["score"] or 0),
                    "breakdown": result.breakdown,
                    "rejected": result.rejected,
                    "reject_reason": result.reject_reason,
                }
            )
        scored.sort(key=lambda x: x["new_score"], reverse=True)
        return scored
