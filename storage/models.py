"""SQLAlchemy ORM models for Deal Hunter."""

from sqlalchemy import JSON, ForeignKey, Index, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Offer(Base):
    __tablename__ = "offers"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    raw_title: Mapped[str] = mapped_column(Text, nullable=False)
    current_price_pln: Mapped[int | None] = mapped_column(default=None)
    url: Mapped[str | None] = mapped_column(Text, default=None)
    source: Mapped[str | None] = mapped_column(String, default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    image_url: Mapped[str | None] = mapped_column(Text, default=None)
    profile: Mapped[str | None] = mapped_column(String, default=None)
    score: Mapped[int | None] = mapped_column(default=None)
    category: Mapped[str | None] = mapped_column(String, default=None)
    status: Mapped[str] = mapped_column(String, default="active")
    first_seen_at: Mapped[str | None] = mapped_column(String, default=None)
    last_seen_at: Mapped[str | None] = mapped_column(String, default=None)

    # New in A2:
    # NOTE: product_id FK to products.id is managed by Alembic migration 004;
    # the constraint is omitted here so Base.metadata.create_all() works in tests
    # before the Product model exists (Tasks 7-10).
    product_id: Mapped[str | None] = mapped_column(String, default=None)
    source_native_id: Mapped[str | None] = mapped_column(String, default=None)
    current_price_original: Mapped[int | None] = mapped_column(default=None)
    currency_original: Mapped[str] = mapped_column(String, default="PLN", server_default="PLN")
    fx_rate_used: Mapped[float | None] = mapped_column(default=None)
    availability: Mapped[str | None] = mapped_column(String, default=None)
    attributes_hint: Mapped[dict | None] = mapped_column(JSON, default=None)
    is_active: Mapped[int] = mapped_column(default=1, server_default="1")

    prices: Mapped[list["PricePoint"]] = relationship(back_populates="offer")
    feedback_entries: Mapped[list["Feedback"]] = relationship(back_populates="offer")
    watchlist_entry: Mapped["WatchlistItem | None"] = relationship(back_populates="offer")

    __table_args__ = (Index("idx_offers_profile_score", "profile", "score"),)


class PricePoint(Base):
    __tablename__ = "price_points"

    offer_id: Mapped[str] = mapped_column(String, ForeignKey("offers.id"), primary_key=True)
    price_pln: Mapped[int] = mapped_column(nullable=False)
    recorded_at: Mapped[str] = mapped_column(String, primary_key=True)

    # New in A2:
    # NOTE: product_id FK is omitted here (see Offer.product_id note above).
    product_id: Mapped[str | None] = mapped_column(String, default=None)
    price_original: Mapped[int | None] = mapped_column(default=None)
    currency_original: Mapped[str] = mapped_column(String, default="PLN", server_default="PLN")
    fx_rate_used: Mapped[float | None] = mapped_column(default=None)
    availability: Mapped[str | None] = mapped_column(String, default=None)

    offer: Mapped["Offer"] = relationship(back_populates="prices")


class Feedback(Base):
    __tablename__ = "feedback"

    deal_id: Mapped[str] = mapped_column(String, ForeignKey("offers.id"), primary_key=True)
    action: Mapped[str | None] = mapped_column(String, default=None)
    created_at: Mapped[str] = mapped_column(String, primary_key=True)

    offer: Mapped["Offer"] = relationship(back_populates="feedback_entries")


class AlertQueue(Base):
    __tablename__ = "alert_queue"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    profile: Mapped[str] = mapped_column(String, nullable=False)
    alert_type: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    sent_at: Mapped[str | None] = mapped_column(String, default=None)


class WatchlistItem(Base):
    __tablename__ = "watchlist"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    deal_id: Mapped[str] = mapped_column(
        String, ForeignKey("offers.id"), nullable=False, unique=True
    )
    target_price: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    triggered_at: Mapped[str | None] = mapped_column(String, default=None)

    offer: Mapped["Offer"] = relationship(back_populates="watchlist_entry")


class SeenDeal(Base):
    """Replaces JSON state files for seen-deal tracking."""

    __tablename__ = "seen_deals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    deal_id: Mapped[str] = mapped_column(String, nullable=False)
    profile: Mapped[str] = mapped_column(String, nullable=False)
    dedup_key: Mapped[str] = mapped_column(String, nullable=False)
    first_seen_at: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (Index("idx_seen_deals_profile_deal", "profile", "deal_id"),)
