"""Offer repository — query + mutation wrapper for the offers table."""

from collections.abc import Iterator
from datetime import datetime
from typing import Any, cast

from sqlalchemy import func, select, text, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from deal_hunter.storage.models import Offer, compute_callback_token


class OfferRepository:
    """Query and mutation wrapper for the offers table."""

    SORT_COLUMNS: dict[str, Any] = {
        "title": Offer.raw_title,
        "price": Offer.current_price_pln,
        "source": Offer.source,
        "profile": Offer.profile,
        "score": Offer.score,
        "status": Offer.status,
        "date": Offer.first_seen_at,
    }

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
            if not existing.callback_token:
                existing.callback_token = compute_callback_token(id)
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
            callback_token=compute_callback_token(id),
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
        sort: str | None = None,
        direction: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[dict]:
        """Query offers with optional filters, sorting, and pagination."""
        stmt = select(Offer)
        stmt = self._apply_filters(
            stmt,
            profile=profile,
            source=source,
            min_score=min_score,
            category=category,
            status=status,
        )
        stmt = stmt.order_by(*self._sort_clause(sort, direction))
        if limit is not None:
            stmt = stmt.limit(limit)
            if offset is not None:
                stmt = stmt.offset(offset)
        return [self._to_dict(d) for d in self.session.scalars(stmt)]

    def get_filtered_ids(
        self,
        *,
        profile: str | None = None,
        source: str | None = None,
        min_score: int | None = None,
        category: str | None = None,
        status: str | None = None,
    ) -> list[str]:
        """Return offer ids matching filters (ordering irrelevant — used for selection)."""
        stmt = select(Offer.id)
        stmt = self._apply_filters(
            stmt,
            profile=profile,
            source=source,
            min_score=min_score,
            category=category,
            status=status,
        )
        return list(self.session.scalars(stmt))

    def bulk_update_status(self, ids: list[str], status: str) -> int:
        """Bulk-update status for a list of offer ids. Returns rows updated."""
        if not ids:
            return 0
        stmt = update(Offer).where(Offer.id.in_(ids)).values(status=status)
        result = self.session.execute(stmt)
        # `update()` returns a CursorResult at runtime, but the 2.0-typed
        # Session.execute signature widens it to Result; cast for mypy.
        return cast("CursorResult[Any]", result).rowcount or 0

    def iter_filtered(
        self,
        *,
        chunk: int = 1000,
        profile: str | None = None,
        source: str | None = None,
        min_score: int | None = None,
        category: str | None = None,
        status: str | None = None,
        sort: str | None = None,
        direction: str | None = None,
    ) -> Iterator[dict]:
        """Stream offers matching filters without materializing whole set in memory."""
        stmt = select(Offer)
        stmt = self._apply_filters(
            stmt,
            profile=profile,
            source=source,
            min_score=min_score,
            category=category,
            status=status,
        )
        stmt = stmt.order_by(*self._sort_clause(sort, direction))
        stmt = stmt.execution_options(yield_per=chunk)
        for offer in self.session.scalars(stmt):
            yield self._to_dict(offer)

    def _sort_clause(self, sort: str | None, direction: str | None) -> list[Any]:
        """Build ORDER BY clause with NULLS LAST and stable id tiebreaker."""
        col = self.SORT_COLUMNS.get(sort or "", None) if sort else None
        desc = (direction or "desc").lower() == "desc"
        if col is None:
            col = Offer.score
            desc = True
        null_marker = col.is_(None)
        ordered = col.desc() if desc else col.asc()
        return [null_marker, ordered, Offer.id]

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

    def resolve_callback_deal_id(self, deal_ref: str) -> str | None:
        """Resolve raw or shortened Telegram callback deal reference to offer id.

        Fast path is an indexed lookup on `callback_token`. Falls back to a
        linear rescan when the column is NULL (older rows before the
        005 migration has run on that session).
        """
        if self.session.get(Offer, deal_ref):
            return deal_ref

        if not deal_ref.startswith("id:"):
            return None

        token = deal_ref[3:]
        if not token:
            return None

        matches = list(
            self.session.scalars(select(Offer.id).where(Offer.callback_token == token).limit(2))
        )
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            return None  # ambiguous — refuse to guess

        # Fallback: recompute for any rows that haven't been backfilled yet.
        stale = list(self.session.scalars(select(Offer.id).where(Offer.callback_token.is_(None))))
        if not stale:
            return None
        stale_matches = [i for i in stale if compute_callback_token(i) == token]
        if len(stale_matches) == 1:
            return stale_matches[0]
        return None

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
