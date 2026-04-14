"""Price repository — query wrapper for price_points (history, drops, sparklines)."""

from datetime import datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from deal_hunter.storage.models import PricePoint


class PriceRepository:
    """Query and mutation wrapper for price_points table."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def record(self, deal_id: str, price: int) -> None:
        """Append a price entry to history."""
        now = datetime.now().isoformat()
        self.session.execute(
            text(
                "INSERT OR IGNORE INTO price_points (offer_id, price_pln, recorded_at)"
                " VALUES (:offer_id, :price_pln, :recorded_at)"
            ),
            {"offer_id": deal_id, "price_pln": price, "recorded_at": now},
        )

    def get_history(self, deal_id: str) -> list[dict]:
        """Get price history ordered chronologically."""
        stmt = (
            select(PricePoint)
            .where(PricePoint.offer_id == deal_id)
            .order_by(PricePoint.recorded_at)
        )
        return [
            {"deal_id": p.offer_id, "price": p.price_pln, "recorded_at": p.recorded_at}
            for p in self.session.scalars(stmt)
        ]

    def get_lowest(self, deal_id: str) -> int | None:
        """Get lowest price ever recorded for a deal."""
        result = self.session.execute(
            select(func.min(PricePoint.price_pln)).where(PricePoint.offer_id == deal_id)
        ).scalar()
        return int(result) if result is not None else None

    def get_previous_price(self, deal_id: str) -> int | None:
        """Get the most recent price before the current one."""
        rows = (
            self.session.execute(
                select(PricePoint.price_pln)
                .where(PricePoint.offer_id == deal_id)
                .order_by(PricePoint.recorded_at.desc())
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
            select(PricePoint)
            .where(PricePoint.offer_id.in_(deal_ids))
            .order_by(PricePoint.recorded_at)
        )
        for p in self.session.scalars(stmt):
            result[p.offer_id].append(
                {"deal_id": p.offer_id, "price": p.price_pln, "recorded_at": p.recorded_at}
            )
        return result

    def get_lowest_prices_batch(self, deal_ids: list[str]) -> dict[str, int | None]:
        """Fetch lowest price for multiple deals in one query."""
        if not deal_ids:
            return {}
        result: dict[str, int | None] = {did: None for did in deal_ids}
        rows = self.session.execute(
            select(PricePoint.offer_id, func.min(PricePoint.price_pln).label("lowest"))
            .where(PricePoint.offer_id.in_(deal_ids))
            .group_by(PricePoint.offer_id)
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
        params: dict[str, Any] = {f"id_{i}": did for i, did in enumerate(deal_ids)}
        params["limit"] = limit
        rows = self.session.execute(
            text(
                f"SELECT offer_id, price_pln FROM ("  # noqa: S608
                f" SELECT offer_id, price_pln, recorded_at,"
                f" ROW_NUMBER() OVER (PARTITION BY offer_id ORDER BY recorded_at DESC) as rn"
                f" FROM price_points"
                f" WHERE offer_id IN ({placeholders})"
                f") WHERE rn <= :limit ORDER BY offer_id, recorded_at"
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
            "WITH ranked AS ( SELECT ph.offer_id, ph.price_pln, ph.recorded_at,"  # noqa: S608
            " LAG(ph.price_pln) OVER (PARTITION BY ph.offer_id ORDER BY ph.recorded_at)"
            " as prev_price,"
            " MIN(ph.price_pln) OVER (PARTITION BY ph.offer_id) as lowest_price,"
            " ROW_NUMBER() OVER (PARTITION BY ph.offer_id ORDER BY ph.recorded_at DESC)"
            " as rn FROM price_points ph JOIN offers d ON ph.offer_id = d.id"
            f" WHERE 1=1 {profile_filter}"
            ") SELECT d.id, d.raw_title AS title, d.current_price_pln AS price,"
            " d.url AS link, d.source, d.description, d.image_url, d.profile,"
            " d.score, d.category, d.status,"
            " d.first_seen_at AS first_seen, d.last_seen_at AS last_seen,"
            " ranked.price_pln as new_price, ranked.prev_price,"
            " ranked.lowest_price, ranked.recorded_at as drop_date"
            " FROM ranked JOIN offers d ON d.id = ranked.offer_id"
            " WHERE ranked.prev_price IS NOT NULL"
            " AND ranked.price_pln < ranked.prev_price"
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
                    SELECT ph.offer_id, ph.price_pln, ph.recorded_at,
                           LAG(ph.price_pln) OVER (
                               PARTITION BY ph.offer_id ORDER BY ph.recorded_at
                           ) as prev_price,
                           ROW_NUMBER() OVER (
                               PARTITION BY ph.offer_id ORDER BY ph.recorded_at DESC
                           ) as rn
                    FROM price_points ph
                )
                SELECT COUNT(*) FROM ranked
                WHERE prev_price IS NOT NULL AND price_pln < prev_price AND rn = 1
                  AND recorded_at >= :cutoff"""
            ),
            {"cutoff": cutoff},
        ).scalar()
        return result or 0
