"""Domain-organized repository classes for Deal Hunter."""

from datetime import datetime

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from storage.models import (
    Deal,
    PriceHistory,
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


class PriceRepository:
    """Query and mutation wrapper for price_history table."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def record(self, deal_id: str, price: int) -> None:
        """Append a price entry to history."""
        now = datetime.now().isoformat()
        self.session.execute(
            text(
                "INSERT OR IGNORE INTO price_history (deal_id, price, recorded_at)"
                " VALUES (:deal_id, :price, :recorded_at)"
            ),
            {"deal_id": deal_id, "price": price, "recorded_at": now},
        )

    def get_history(self, deal_id: str) -> list[dict]:
        """Get price history ordered chronologically."""
        stmt = (
            select(PriceHistory)
            .where(PriceHistory.deal_id == deal_id)
            .order_by(PriceHistory.recorded_at)
        )
        return [
            {"deal_id": p.deal_id, "price": p.price, "recorded_at": p.recorded_at}
            for p in self.session.scalars(stmt)
        ]

    def get_lowest(self, deal_id: str) -> int | None:
        """Get lowest price ever recorded for a deal."""
        result = self.session.execute(
            select(func.min(PriceHistory.price)).where(PriceHistory.deal_id == deal_id)
        ).scalar()
        return int(result) if result is not None else None

    def get_previous_price(self, deal_id: str) -> int | None:
        """Get the most recent price before the current one."""
        rows = (
            self.session.execute(
                select(PriceHistory.price)
                .where(PriceHistory.deal_id == deal_id)
                .order_by(PriceHistory.recorded_at.desc())
                .limit(2)
            )
            .scalars()
            .all()
        )
        return int(rows[1]) if len(rows) >= 2 else None

    def get_histories_batch(self, deal_ids: list[str]) -> dict[str, list[dict]]:
        """Fetch price history for multiple deals in one query."""
        if not deal_ids:
            return {}
        result: dict[str, list[dict]] = {did: [] for did in deal_ids}
        stmt = (
            select(PriceHistory)
            .where(PriceHistory.deal_id.in_(deal_ids))
            .order_by(PriceHistory.recorded_at)
        )
        for p in self.session.scalars(stmt):
            result[p.deal_id].append(
                {"deal_id": p.deal_id, "price": p.price, "recorded_at": p.recorded_at}
            )
        return result

    def get_lowest_prices_batch(self, deal_ids: list[str]) -> dict[str, int | None]:
        """Fetch lowest price for multiple deals in one query."""
        if not deal_ids:
            return {}
        result: dict[str, int | None] = {did: None for did in deal_ids}
        rows = self.session.execute(
            select(PriceHistory.deal_id, func.min(PriceHistory.price).label("lowest"))
            .where(PriceHistory.deal_id.in_(deal_ids))
            .group_by(PriceHistory.deal_id)
        ).all()
        for row in rows:
            result[row[0]] = int(row[1])
        return result

    def get_sparkline_data_batch(
        self, deal_ids: list[str], limit: int = 10
    ) -> dict[str, list[int]]:
        """Fetch last N price points per deal for sparkline rendering."""
        if not deal_ids:
            return {}
        placeholders = ",".join(f":id_{i}" for i in range(len(deal_ids)))
        params = {f"id_{i}": did for i, did in enumerate(deal_ids)}
        params["limit"] = limit
        rows = self.session.execute(
            text(
                f"SELECT deal_id, price FROM ("  # noqa: S608
                f" SELECT deal_id, price, recorded_at,"
                f" ROW_NUMBER() OVER (PARTITION BY deal_id ORDER BY recorded_at DESC) as rn"
                f" FROM price_history"
                f" WHERE deal_id IN ({placeholders})"
                f") WHERE rn <= :limit ORDER BY deal_id, recorded_at"
            ),
            params,
        ).all()
        result: dict[str, list[int]] = {}
        for row in rows:
            result.setdefault(row[0], []).append(row[1])
        return result

    def get_drops(
        self,
        *,
        days: int = 7,
        profile: str | None = None,
        min_drop_percent: float = 0,
    ) -> list[dict]:
        """Get price drops in the last N days using window functions (single query, no N+1).

        Uses LAG() for previous price and MIN() OVER for lowest-ever detection.
        """
        from datetime import timedelta

        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        profile_filter = "AND d.profile = :profile" if profile else ""
        params: dict = {"cutoff": cutoff}
        if profile:
            params["profile"] = profile

        sql = (  # noqa: S608
            "WITH ranked AS ( SELECT ph.deal_id, ph.price, ph.recorded_at,"  # noqa: S608
            " LAG(ph.price) OVER (PARTITION BY ph.deal_id ORDER BY ph.recorded_at)"
            " as prev_price,"
            " MIN(ph.price) OVER (PARTITION BY ph.deal_id) as lowest_price,"
            " ROW_NUMBER() OVER (PARTITION BY ph.deal_id ORDER BY ph.recorded_at DESC)"
            " as rn FROM price_history ph JOIN deals d ON ph.deal_id = d.id"
            f" WHERE 1=1 {profile_filter}"
            ") SELECT d.*, ranked.price as new_price, ranked.prev_price,"
            " ranked.lowest_price, ranked.recorded_at as drop_date"
            " FROM ranked JOIN deals d ON d.id = ranked.deal_id"
            " WHERE ranked.prev_price IS NOT NULL"
            " AND ranked.price < ranked.prev_price"
            " AND ranked.recorded_at >= :cutoff"
            " AND ranked.rn = 1 ORDER BY ranked.recorded_at DESC"
        )
        rows = self.session.execute(text(sql), params).mappings().all()

        results = []
        for row in rows:
            old_price = row["prev_price"]
            new_price = row["new_price"]
            diff_pln = old_price - new_price
            diff_percent = (diff_pln / old_price) * 100 if old_price > 0 else 0

            if diff_percent < min_drop_percent:
                continue

            results.append(
                {
                    "id": row["id"],
                    "title": row["title"],
                    "price": row["price"],
                    "link": row["link"],
                    "source": row["source"],
                    "description": row["description"],
                    "image_url": row["image_url"],
                    "profile": row["profile"],
                    "score": row["score"],
                    "category": row["category"],
                    "status": row["status"],
                    "first_seen": row["first_seen"],
                    "last_seen": row["last_seen"],
                    "old_price": old_price,
                    "new_price": new_price,
                    "diff_pln": diff_pln,
                    "diff_percent": round(diff_percent, 1),
                    "is_lowest_ever": new_price <= row["lowest_price"],
                    "drop_date": row["drop_date"],
                }
            )
        return results

    def count_drops(self, days: int = 7) -> int:
        """Count deals with price drops in last N days (efficient COUNT)."""
        from datetime import timedelta

        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        result = self.session.execute(
            text(
                """WITH ranked AS (
                    SELECT ph.deal_id, ph.price, ph.recorded_at,
                           LAG(ph.price) OVER (
                               PARTITION BY ph.deal_id ORDER BY ph.recorded_at
                           ) as prev_price,
                           ROW_NUMBER() OVER (
                               PARTITION BY ph.deal_id ORDER BY ph.recorded_at DESC
                           ) as rn
                    FROM price_history ph
                )
                SELECT COUNT(*) FROM ranked
                WHERE prev_price IS NOT NULL AND price < prev_price AND rn = 1
                  AND recorded_at >= :cutoff"""
            ),
            {"cutoff": cutoff},
        ).scalar()
        return result or 0
