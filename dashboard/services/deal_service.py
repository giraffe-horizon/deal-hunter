"""Deal-related business logic for the Deal Hunter dashboard."""

import math
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from storage.repositories import DealRepository, PriceRepository


@dataclass
class DealsPageData:
    """All data needed to render the deals listing page."""

    deals: list[dict]
    sparklines: dict[str, list[int]]
    page: int
    total_pages: int
    total_filtered: int
    filter_params: str
    # Stats (only populated for full page, not HTMX partials)
    total_deals: int = 0
    high_score_pct: int = 0
    new_today: int = 0
    drops_count: int = 0
    # Filter dropdown options
    sources: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)


@dataclass
class PriceDropsData:
    """All data needed to render the price drops view."""

    drops: list[dict]
    days: int
    total_drops: int
    avg_drop_pct: float
    biggest_drop: int
    categories: dict[str, int]
    category_trends: dict[str, list[dict]]


class DealService:
    """Encapsulates deal-related business logic."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.deals = DealRepository(session)
        self.prices = PriceRepository(session)

    # ── Deals listing page ──────────────────────────────────

    def get_deals_page(
        self,
        *,
        profile: str | None = None,
        source: str | None = None,
        min_score: int | None = None,
        category: str | None = None,
        status: str | None = None,
        page: int = 1,
        per_page: int = 50,
        score_threshold: int = 70,
        include_stats: bool = False,
    ) -> DealsPageData:
        """Build the full deals listing payload (filtering, pagination, sparklines).

        When *include_stats* is True the returned object also carries aggregate
        stats and filter-dropdown options needed for the full page render (not
        needed for HTMX partial refreshes).
        """
        # Normalize
        profile = profile or None
        source = source or None
        category = category or None
        status = status or None
        page = max(1, page)

        offset = (page - 1) * per_page
        deals = self.deals.get_filtered(
            profile=profile,
            source=source,
            min_score=min_score,
            category=category,
            status=status,
            limit=per_page,
            offset=offset,
        )
        total_filtered = self.deals.count(
            profile=profile,
            source=source,
            min_score=min_score,
            category=category,
            status=status,
        )
        total_pages = max(1, math.ceil(total_filtered / per_page))

        filter_params = self._build_filter_params(
            profile=profile,
            source=source,
            min_score=min_score,
            category=category,
            status=status,
        )

        sparklines = self.get_sparklines(deals)

        data = DealsPageData(
            deals=deals,
            sparklines=sparklines,
            page=page,
            total_pages=total_pages,
            total_filtered=total_filtered,
            filter_params=filter_params,
        )

        if include_stats:
            agg = self.get_stats(score_threshold=score_threshold)
            data.total_deals = agg["total_deals"]
            data.high_score_pct = agg["high_score_pct"]
            data.new_today = agg["new_today"]
            data.drops_count = agg["drops_count"]

            filter_opts = self.deals.get_filter_options()
            data.sources = filter_opts["sources"]
            data.categories = filter_opts["categories"]

        return data

    @staticmethod
    def _build_filter_params(
        *,
        profile: str | None,
        source: str | None,
        min_score: int | None,
        category: str | None,
        status: str | None,
    ) -> str:
        """Build query-string fragment for pagination links."""
        parts: list[str] = []
        if profile:
            parts.append(f"&profile={profile}")
        if source:
            parts.append(f"&source={source}")
        if min_score is not None:
            parts.append(f"&min_score={min_score}")
        if category:
            parts.append(f"&category={category}")
        if status:
            parts.append(f"&status={status}")
        return "".join(parts)

    # ── Stats ───────────────────────────────────────────────

    def get_stats(self, *, score_threshold: int = 70) -> dict:
        """Return aggregate dashboard stats (total, high_score_pct, new_today, drops_count)."""
        stats = self.deals.get_stats(score_threshold=score_threshold)
        total = stats["total"]
        return {
            "total_deals": total,
            "high_score_pct": round(stats["high_score"] / total * 100) if total else 0,
            "new_today": stats["new_today"],
            "drops_count": self.prices.count_drops(days=7),
        }

    # ── Price drops view ────────────────────────────────────

    def get_price_drops(self, *, days: int = 7) -> PriceDropsData:
        """Build the price-drops view payload (drops, stats, categories, trends)."""
        drops = self.prices.get_drops(days=days)
        all_deals = self.deals.get_filtered()

        total_drops = len(drops)
        avg_drop_pct = (
            round(sum(d["diff_percent"] for d in drops) / total_drops, 1) if total_drops else 0
        )
        biggest_drop = max((d["diff_pln"] for d in drops), default=0)

        # Category distribution
        categories: dict[str, int] = {}
        for deal in all_deals:
            cat = deal.get("category") or "Uncategorized"
            categories[cat] = categories.get(cat, 0) + 1
        categories = dict(sorted(categories.items(), key=lambda x: x[1], reverse=True))

        # Price trends for top 3 categories
        category_trends: dict[str, list[dict]] = {}
        for cat_name in list(categories.keys())[:3]:
            trend = self.deals.get_category_price_trend(cat_name, days=30)
            if trend:
                category_trends[cat_name] = trend

        return PriceDropsData(
            drops=drops,
            days=days,
            total_drops=total_drops,
            avg_drop_pct=avg_drop_pct,
            biggest_drop=biggest_drop,
            categories=categories,
            category_trends=category_trends,
        )

    # ── Comparison / sparklines / scoring ───────────────────

    def get_comparison_data(self, deal_ids: list[str]) -> dict:
        """Batch-fetch deals, price histories, and lowest prices."""
        deal_ids = deal_ids[:5]
        deals = self.deals.get_by_ids(deal_ids) if deal_ids else []
        id_list = [d["id"] for d in deals]
        return {
            "deals": deals,
            "price_histories": self.prices.get_histories_batch(id_list),
            "lowest_prices": self.prices.get_lowest_prices_batch(id_list),
        }

    def get_sparklines(self, deals: list[dict]) -> dict[str, list[int]]:
        """Get sparkline price data for a list of deals."""
        ids = [d.get("id") or d.get("deal_id") for d in deals]
        return self.prices.get_sparkline_data_batch([i for i in ids if i])

    def score_single_deal(self, deal_dict: dict) -> dict | None:
        """Re-score a deal using its profile config. Returns breakdown or None."""
        from dashboard.dependencies import safe_load_profile

        profile_data = safe_load_profile(deal_dict.get("profile", ""))
        if not profile_data:
            return None
        from filters.base import BaseFilter
        from sources.base import Deal

        deal_obj = Deal(
            id=deal_dict["id"],
            title=deal_dict["title"],
            price=deal_dict["price"] or 0,
            link=deal_dict["link"] or "",
            source=deal_dict["source"] or "",
            description=deal_dict["description"] or "",
            temperature=0,
            image_url=deal_dict.get("image_url") or "",
            published_at="",
        )
        result = BaseFilter(profile_data).score_deal(deal_obj)
        return {
            "score": result.score,
            "breakdown": result.breakdown,
            "rejected": result.rejected,
            "reject_reason": result.reject_reason,
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
