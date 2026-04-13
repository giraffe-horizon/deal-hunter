"""Domain-organized repository classes for Deal Hunter."""

from datetime import datetime

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from storage.models import (
    Deal,
)


class DealRepository:
    """Query and mutation wrapper for the deals table."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(  # noqa: A002
        self,
        *,
        id: str,  # noqa: A002
        title: str,
        price: int,
        link: str = "",
        source: str = "",
        description: str = "",
        image_url: str = "",
        profile: str = "",
        score: int = 0,
        category: str = "",
        status: str = "active",
        first_seen: str = "",
        last_seen: str = "",
    ) -> Deal:
        """Insert a new deal or update last_seen, score, and price if changed."""
        now = last_seen or datetime.now().isoformat()
        existing = self.session.get(Deal, id)

        if existing:
            old_price = existing.price
            existing.last_seen = now
            existing.score = score
            existing.price = price
            # Do NOT reset status — preserve user-set status (watching, rejected, etc.)
            if old_price and price and old_price != price:
                self._record_price(id, price, now)
            return existing

        deal = Deal(
            id=id,
            title=title,
            price=price,
            link=link,
            source=source,
            description=description,
            image_url=image_url,
            profile=profile,
            score=score,
            category=category,
            status=status,
            first_seen=first_seen or now,
            last_seen=now,
        )
        self.session.add(deal)
        if price:
            self._record_price(id, price, now)
        return deal

    def _record_price(self, deal_id: str, price: int, recorded_at: str) -> None:
        """Append price to history, ignoring duplicates."""
        self.session.execute(
            text(
                "INSERT OR IGNORE INTO price_history (deal_id, price, recorded_at)"
                " VALUES (:deal_id, :price, :recorded_at)"
            ),
            {"deal_id": deal_id, "price": price, "recorded_at": recorded_at},
        )

    def get_by_id(self, deal_id: str) -> dict | None:
        """Get a single deal as dict, or None."""
        deal = self.session.get(Deal, deal_id)
        return self._to_dict(deal) if deal else None

    def get_by_ids(self, ids: list[str]) -> list[dict]:
        """Fetch multiple deals by ID."""
        if not ids:
            return []
        stmt = select(Deal).where(Deal.id.in_(ids))
        return [self._to_dict(d) for d in self.session.scalars(stmt)]

    def get_filtered(
        self,
        *,
        profile: str | None = None,
        source: str | None = None,
        min_score: int | None = None,
        category: str | None = None,
        status: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[dict]:
        """Query deals with optional filters and pagination."""
        stmt = select(Deal)
        stmt = self._apply_filters(
            stmt,
            profile=profile,
            source=source,
            min_score=min_score,
            category=category,
            status=status,
        )
        stmt = stmt.order_by(Deal.score.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
            if offset is not None:
                stmt = stmt.offset(offset)
        return [self._to_dict(d) for d in self.session.scalars(stmt)]

    def count(
        self,
        *,
        profile: str | None = None,
        source: str | None = None,
        min_score: int | None = None,
        category: str | None = None,
        status: str | None = None,
    ) -> int:
        """Count deals matching filters."""
        stmt = select(func.count()).select_from(Deal)
        stmt = self._apply_filters(
            stmt,
            profile=profile,
            source=source,
            min_score=min_score,
            category=category,
            status=status,
        )
        return self.session.execute(stmt).scalar() or 0

    def get_stats(self, score_threshold: int = 70) -> dict:
        """Get aggregate deal statistics."""
        today = datetime.now().strftime("%Y-%m-%d")
        row = (
            self.session.execute(
                text(
                    """SELECT
                    COUNT(*) as total,
                    COALESCE(SUM(CASE WHEN score >= :threshold THEN 1 ELSE 0 END), 0)
                        as high_score,
                    COALESCE(SUM(CASE WHEN first_seen LIKE :today THEN 1 ELSE 0 END), 0)
                        as new_today
                FROM deals"""
                ),
                {"threshold": score_threshold, "today": f"{today}%"},
            )
            .mappings()
            .first()
        )
        return dict(row) if row else {"total": 0, "high_score": 0, "new_today": 0}

    def update_status(self, deal_id: str, status: str) -> bool:
        """Update a deal's status. Returns True if deal existed."""
        deal = self.session.get(Deal, deal_id)
        if not deal:
            return False
        deal.status = status
        return True

    def get_by_status(self, status: str, limit: int = 20) -> list[dict]:
        """Get deals filtered by status, ordered by last_seen descending."""
        stmt = (
            select(Deal).where(Deal.status == status).order_by(Deal.last_seen.desc()).limit(limit)
        )
        return [self._to_dict(d) for d in self.session.scalars(stmt)]

    def get_filter_options(self) -> dict:
        """Get distinct sources and categories for filter dropdowns."""
        sources = [
            r[0]
            for r in self.session.execute(
                select(Deal.source)
                .where(Deal.source.isnot(None), Deal.source != "")
                .distinct()
                .order_by(Deal.source)
            )
        ]
        categories = [
            r[0]
            for r in self.session.execute(
                select(Deal.category)
                .where(Deal.category.isnot(None), Deal.category != "")
                .distinct()
                .order_by(Deal.category)
            )
        ]
        return {"sources": sources, "categories": categories}

    def get_category_price_trend(self, category: str, days: int = 30) -> list[dict]:
        """Get daily average price for a category over the last N days."""
        from datetime import timedelta

        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        rows = (
            self.session.execute(
                text(
                    """SELECT DATE(ph.recorded_at) as day, AVG(ph.price) as avg_price
                FROM price_history ph
                JOIN deals d ON ph.deal_id = d.id
                WHERE d.category = :category AND ph.recorded_at >= :cutoff
                GROUP BY DATE(ph.recorded_at)
                ORDER BY day"""
                ),
                {"category": category, "cutoff": cutoff},
            )
            .mappings()
            .all()
        )
        return [{"day": r["day"], "avg_price": round(r["avg_price"])} for r in rows]

    def _apply_filters(self, stmt, *, profile, source, min_score, category, status):
        """Apply optional WHERE clauses to a statement."""
        if profile is not None:
            stmt = stmt.where(Deal.profile == profile)
        if source is not None:
            stmt = stmt.where(Deal.source == source)
        if min_score is not None:
            stmt = stmt.where(Deal.score >= min_score)
        if category is not None:
            stmt = stmt.where(Deal.category == category)
        if status is not None:
            stmt = stmt.where(Deal.status == status)
        return stmt

    @staticmethod
    def _to_dict(deal: Deal) -> dict:
        return {
            "id": deal.id,
            "title": deal.title,
            "price": deal.price,
            "link": deal.link,
            "source": deal.source,
            "description": deal.description,
            "image_url": deal.image_url,
            "profile": deal.profile,
            "score": deal.score,
            "category": deal.category,
            "status": deal.status,
            "first_seen": deal.first_seen,
            "last_seen": deal.last_seen,
        }
