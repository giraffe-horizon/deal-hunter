"""Domain-organized repository classes for Deal Hunter."""

from datetime import datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from storage.models import (
    AlertQueue,
    Feedback,
    Offer,
    PricePoint,
    SeenDeal,
    WatchlistItem,
)


class OfferRepository:
    """Query and mutation wrapper for the offers table."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(  # noqa: A002
        self,
        *,
        id: str,  # noqa: A002
        raw_title: str | None = None,
        title: str | None = None,  # legacy
        current_price_pln: int | None = None,
        price: int | None = None,  # legacy
        url: str = "",
        link: str = "",  # legacy
        source: str = "",
        description: str = "",
        image_url: str = "",
        profile: str = "",
        score: int = 0,
        category: str = "",
        status: str = "active",
        first_seen_at: str = "",
        first_seen: str = "",  # legacy
        last_seen_at: str = "",
        last_seen: str = "",  # legacy
    ) -> Offer:
        """Insert a new offer or update last_seen_at, score, and price if changed."""
        # Normalize legacy kwarg aliases to canonical names
        raw_title = raw_title if raw_title is not None else title
        current_price_pln = current_price_pln if current_price_pln is not None else price
        url = url or link
        first_seen_at = first_seen_at or first_seen
        last_seen_at = last_seen_at or last_seen
        if raw_title is None:
            raise TypeError("OfferRepository.upsert requires raw_title or title")

        now = last_seen_at or datetime.now().isoformat()
        existing: Offer | None = self.session.get(Offer, id)

        if existing:
            old_price = existing.current_price_pln
            existing.last_seen_at = now
            existing.score = score
            existing.current_price_pln = current_price_pln
            # Do NOT reset status — preserve user-set status (watching, rejected, etc.)
            if old_price and current_price_pln and old_price != current_price_pln:
                self._record_price(id, current_price_pln, now)
            return existing

        offer = Offer(
            id=id,
            raw_title=raw_title,
            current_price_pln=current_price_pln,
            url=url,
            source=source,
            description=description,
            image_url=image_url,
            profile=profile,
            score=score,
            category=category,
            status=status,
            first_seen_at=first_seen_at or now,
            last_seen_at=now,
        )
        self.session.add(offer)
        if current_price_pln:
            self._record_price(id, current_price_pln, now)
        return offer

    def _record_price(self, deal_id: str, price: int, recorded_at: str) -> None:
        """Append price to history, ignoring duplicates."""
        self.session.flush()  # ensure offer row exists before FK insert
        self.session.execute(
            text(
                "INSERT OR IGNORE INTO price_points (offer_id, price_pln, recorded_at)"
                " VALUES (:offer_id, :price_pln, :recorded_at)"
            ),
            {"offer_id": deal_id, "price_pln": price, "recorded_at": recorded_at},
        )

    def get_by_id(self, deal_id: str) -> dict | None:
        """Get a single offer as dict, or None."""
        offer = self.session.get(Offer, deal_id)
        return self._to_dict(offer) if offer else None

    def get_by_ids(self, ids: list[str]) -> list[dict]:
        """Fetch multiple offers by ID."""
        if not ids:
            return []
        stmt = select(Offer).where(Offer.id.in_(ids))
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
        """Query offers with optional filters and pagination."""
        stmt = select(Offer)
        stmt = self._apply_filters(
            stmt,
            profile=profile,
            source=source,
            min_score=min_score,
            category=category,
            status=status,
        )
        stmt = stmt.order_by(Offer.score.desc())
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
        """Count offers matching filters."""
        stmt = select(func.count()).select_from(Offer)
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
        """Get aggregate offer statistics."""
        today = datetime.now().strftime("%Y-%m-%d")
        row = (
            self.session.execute(
                text(
                    """SELECT
                    COUNT(*) as total,
                    COALESCE(SUM(CASE WHEN score >= :threshold THEN 1 ELSE 0 END), 0)
                        as high_score,
                    COALESCE(SUM(CASE WHEN first_seen_at LIKE :today THEN 1 ELSE 0 END), 0)
                        as new_today
                FROM offers"""
                ),
                {"threshold": score_threshold, "today": f"{today}%"},
            )
            .mappings()
            .first()
        )
        return dict(row) if row else {"total": 0, "high_score": 0, "new_today": 0}

    def update_status(self, deal_id: str, status: str) -> bool:
        """Update an offer's status. Returns True if offer existed."""
        offer = self.session.get(Offer, deal_id)
        if not offer:
            return False
        offer.status = status
        return True

    def get_by_status(self, status: str, limit: int = 20) -> list[dict]:
        """Get offers filtered by status, ordered by last_seen_at descending."""
        stmt = (
            select(Offer)
            .where(Offer.status == status)
            .order_by(Offer.last_seen_at.desc())
            .limit(limit)
        )
        return [self._to_dict(d) for d in self.session.scalars(stmt)]

    def get_filter_options(self) -> dict:
        """Get distinct sources and categories for filter dropdowns."""
        sources = [
            r[0]
            for r in self.session.execute(
                select(Offer.source)
                .where(Offer.source.isnot(None), Offer.source != "")
                .distinct()
                .order_by(Offer.source)
            )
        ]
        categories = [
            r[0]
            for r in self.session.execute(
                select(Offer.category)
                .where(Offer.category.isnot(None), Offer.category != "")
                .distinct()
                .order_by(Offer.category)
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
                    """SELECT DATE(ph.recorded_at) as day, AVG(ph.price_pln) as avg_price
                FROM price_points ph
                JOIN offers d ON ph.offer_id = d.id
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

    def _apply_filters(
        self,
        stmt: Any,
        *,
        profile: str | None,
        source: str | None,
        min_score: int | None,
        category: str | None,
        status: str | None,
    ) -> Any:
        """Apply optional WHERE clauses to a statement."""
        if profile is not None:
            stmt = stmt.where(Offer.profile == profile)
        if source is not None:
            stmt = stmt.where(Offer.source == source)
        if min_score is not None:
            stmt = stmt.where(Offer.score >= min_score)
        if category is not None:
            stmt = stmt.where(Offer.category == category)
        if status is not None:
            stmt = stmt.where(Offer.status == status)
        return stmt

    @staticmethod
    def _to_dict(offer: Offer) -> dict:
        return {
            # Legacy keys — preserved for template/Telegram/bot contract:
            "id": offer.id,
            "title": offer.raw_title,
            "price": offer.current_price_pln,
            "link": offer.url,
            "source": offer.source,
            "description": offer.description,
            "image_url": offer.image_url,
            "profile": offer.profile,
            "score": offer.score,
            "category": offer.category,
            "status": offer.status,
            "first_seen": offer.first_seen_at,
            "last_seen": offer.last_seen_at,
            # New keys — surfaced for product-aware callers:
            "raw_title": offer.raw_title,
            "current_price_pln": offer.current_price_pln,
            "url": offer.url,
            "first_seen_at": offer.first_seen_at,
            "last_seen_at": offer.last_seen_at,
            "product_id": offer.product_id,
            "source_native_id": offer.source_native_id,
            "currency_original": offer.currency_original,
            "current_price_original": offer.current_price_original,
            "fx_rate_used": offer.fx_rate_used,
            "availability": offer.availability,
            "is_active": offer.is_active,
        }


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


class WatchlistRepository:
    """Query and mutation wrapper for watchlist table."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, deal_id: str, target_price: int) -> bool:
        """Add a deal to watchlist. Returns False if already exists."""
        existing = self.session.query(WatchlistItem).filter_by(deal_id=deal_id).first()
        if existing:
            return False
        item = WatchlistItem(
            deal_id=deal_id,
            target_price=target_price,
            created_at=datetime.now().isoformat(),
        )
        self.session.add(item)
        return True

    def remove(self, deal_id: str) -> bool:
        """Remove from watchlist. Returns True if found and removed."""
        item = self.session.query(WatchlistItem).filter_by(deal_id=deal_id).first()
        if not item:
            return False
        self.session.delete(item)
        return True

    def get_all(self) -> list[dict]:
        """Get all watchlist items with deal info."""
        rows = (
            self.session.execute(
                text(
                    """SELECT w.deal_id, w.target_price, w.created_at, w.triggered_at,
                          d.raw_title AS title, d.current_price_pln AS current_price,
                          d.url AS link, d.source
                   FROM watchlist w
                   LEFT JOIN offers d ON w.deal_id = d.id
                   ORDER BY w.created_at DESC"""
                )
            )
            .mappings()
            .all()
        )
        return [dict(r) for r in rows]

    def get_item(self, deal_id: str) -> dict | None:
        """Get a single watchlist item with deal info."""
        row = (
            self.session.execute(
                text(
                    """SELECT w.deal_id, w.target_price, w.created_at, w.triggered_at,
                          d.raw_title AS title, d.current_price_pln AS current_price,
                          d.url AS link, d.source
                   FROM watchlist w
                   LEFT JOIN offers d ON w.deal_id = d.id
                   WHERE w.deal_id = :deal_id"""
                ),
                {"deal_id": deal_id},
            )
            .mappings()
            .first()
        )
        return dict(row) if row else None

    def update_target_price(self, deal_id: str, target_price: int) -> bool:
        """Update target price. Returns True if found."""
        item = self.session.query(WatchlistItem).filter_by(deal_id=deal_id).first()
        if not item:
            return False
        item.target_price = target_price
        self.session.flush()
        return True

    def check_trigger(self, deal_id: str, current_price: int) -> dict | None:
        """Check if current price meets watchlist target. Returns entry if triggered."""
        item = (
            self.session.query(WatchlistItem)
            .filter_by(deal_id=deal_id)
            .filter(WatchlistItem.triggered_at.is_(None))
            .first()
        )
        if item and current_price <= item.target_price:
            return {"deal_id": item.deal_id, "target_price": item.target_price}
        return None

    def mark_triggered(self, deal_id: str) -> None:
        """Mark a watchlist entry as triggered."""
        item = self.session.query(WatchlistItem).filter_by(deal_id=deal_id).first()
        if item:
            item.triggered_at = datetime.now().isoformat()


class AlertQueueRepository:
    """Query and mutation wrapper for alert_queue table."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def queue(self, profile: str, alert_type: str, payload_json: str) -> None:
        """Queue an alert for later sending."""
        alert = AlertQueue(
            profile=profile,
            alert_type=alert_type,
            payload=payload_json,
            created_at=datetime.now().isoformat(),
        )
        self.session.add(alert)

    def get_pending(self, profile: str | None = None) -> list[dict]:
        """Get unsent alerts, ordered by creation time."""
        stmt = select(AlertQueue).where(AlertQueue.sent_at.is_(None))
        if profile is not None:
            stmt = stmt.where(AlertQueue.profile == profile)
        stmt = stmt.order_by(AlertQueue.created_at.asc())
        return [
            {
                "id": a.id,
                "profile": a.profile,
                "alert_type": a.alert_type,
                "payload": a.payload,
                "created_at": a.created_at,
            }
            for a in self.session.scalars(stmt)
        ]

    def mark_sent(self, alert_ids: list[int]) -> None:
        """Mark alerts as sent."""
        if not alert_ids:
            return
        now = datetime.now().isoformat()
        self.session.execute(
            text(
                f"UPDATE alert_queue SET sent_at = :now"  # noqa: S608
                f" WHERE id IN ({','.join(f':id_{i}' for i in range(len(alert_ids)))})"
            ),
            {"now": now, **{f"id_{i}": aid for i, aid in enumerate(alert_ids)}},
        )


class FeedbackRepository:
    """Query and mutation wrapper for feedback table."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def record(self, deal_id: str, action: str) -> None:
        """Record user feedback on a deal."""
        fb = Feedback(
            deal_id=deal_id,
            action=action,
            created_at=datetime.now().isoformat(),
        )
        self.session.add(fb)

    def get_stats(self) -> dict[str, int]:
        """Get counts of feedback actions."""
        rows = self.session.execute(
            select(Feedback.action, func.count().label("cnt")).group_by(Feedback.action)
        ).all()
        return {row[0]: row[1] for row in rows}


class SeenDealRepository:
    """Replaces JSON state files for seen-deal tracking."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def mark_seen(self, deal_id: str, profile: str, dedup_key: str) -> None:
        """Mark a deal as seen for a profile."""
        seen = SeenDeal(
            deal_id=deal_id,
            profile=profile,
            dedup_key=dedup_key,
            first_seen_at=datetime.now().isoformat(),
        )
        self.session.add(seen)

    def is_seen(self, deal_id: str, profile: str) -> bool:
        """Check if a deal has been seen for a profile (within TTL)."""
        from datetime import timedelta

        cutoff = (datetime.now() - timedelta(days=14)).isoformat()
        result = (
            self.session.query(SeenDeal)
            .filter(
                SeenDeal.deal_id == deal_id,
                SeenDeal.profile == profile,
                SeenDeal.first_seen_at > cutoff,
            )
            .first()
        )
        return result is not None

    def get_seen_ids(self, profile: str) -> set[str]:
        """Get all seen deal IDs for a profile (within TTL)."""
        from datetime import timedelta

        cutoff = (datetime.now() - timedelta(days=14)).isoformat()
        rows = (
            self.session.execute(
                select(SeenDeal.deal_id).where(
                    SeenDeal.profile == profile, SeenDeal.first_seen_at > cutoff
                )
            )
            .scalars()
            .all()
        )
        return set(rows)

    def cleanup_expired(self, ttl_days: int = 14) -> int:
        """Delete entries older than TTL. Returns count deleted."""
        from datetime import timedelta

        cutoff = (datetime.now() - timedelta(days=ttl_days)).isoformat()
        result = self.session.execute(
            text("DELETE FROM seen_deals WHERE first_seen_at <= :cutoff"),
            {"cutoff": cutoff},
        )
        return int(result.rowcount)  # type: ignore[attr-defined]
