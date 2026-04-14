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

    # New in A2 (product_id FK restored in Task 7 once Product model exists):
    product_id: Mapped[str | None] = mapped_column(String, ForeignKey("products.id"), default=None)
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
    product: Mapped["Product | None"] = relationship(back_populates="offers")
    payload_history: Mapped[list["OfferPayloadHistory"]] = relationship(
        back_populates="offer", cascade="all, delete-orphan"
    )
    events: Mapped[list["DealEvent"]] = relationship(back_populates="offer")

    __table_args__ = (Index("idx_offers_profile_score", "profile", "score"),)


class PricePoint(Base):
    __tablename__ = "price_points"

    offer_id: Mapped[str] = mapped_column(String, ForeignKey("offers.id"), primary_key=True)
    price_pln: Mapped[int] = mapped_column(nullable=False)
    recorded_at: Mapped[str] = mapped_column(String, primary_key=True)

    # New in A2 (product_id FK restored in Task 7 once Product model exists):
    product_id: Mapped[str | None] = mapped_column(String, ForeignKey("products.id"), default=None)
    price_original: Mapped[int | None] = mapped_column(default=None)
    currency_original: Mapped[str] = mapped_column(String, default="PLN", server_default="PLN")
    fx_rate_used: Mapped[float | None] = mapped_column(default=None)
    availability: Mapped[str | None] = mapped_column(String, default=None)

    offer: Mapped["Offer"] = relationship(back_populates="prices")
    product: Mapped["Product | None"] = relationship(back_populates="price_points")


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


class Product(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    canonical_title: Mapped[str] = mapped_column(Text, nullable=False)
    brand: Mapped[str | None] = mapped_column(String, default=None)
    model: Mapped[str | None] = mapped_column(String, default=None)
    category: Mapped[str] = mapped_column(String, nullable=False)
    attributes: Mapped[dict] = mapped_column(JSON, nullable=False)
    canonical_image_url: Mapped[str | None] = mapped_column(Text, default=None)
    review_status: Mapped[str] = mapped_column(String, default="auto")
    confidence_score: Mapped[float | None] = mapped_column(default=None)
    merged_from: Mapped[list | None] = mapped_column(JSON, default=None)
    archived: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)

    aliases: Mapped[list["ProductAlias"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    offers: Mapped[list["Offer"]] = relationship(back_populates="product")
    price_points: Mapped[list["PricePoint"]] = relationship(back_populates="product")


class ProductAlias(Base):
    __tablename__ = "product_aliases"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[str] = mapped_column(
        String, ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    identifier_type: Mapped[str] = mapped_column(String, nullable=False)
    identifier_value: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str | None] = mapped_column(String, default=None)
    confidence: Mapped[float] = mapped_column(nullable=False)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    product: Mapped["Product"] = relationship(back_populates="aliases")


class OfferPayloadHistory(Base):
    __tablename__ = "offer_payload_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    offer_id: Mapped[str] = mapped_column(
        String, ForeignKey("offers.id", ondelete="CASCADE"), nullable=False
    )
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    captured_at: Mapped[str] = mapped_column(String, nullable=False)

    offer: Mapped["Offer"] = relationship(back_populates="payload_history")


class DealEvent(Base):
    __tablename__ = "deal_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    offer_id: Mapped[str] = mapped_column(String, ForeignKey("offers.id"), nullable=False)
    product_id: Mapped[str | None] = mapped_column(String, ForeignKey("products.id"), default=None)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    price_at_event: Mapped[int | None] = mapped_column(default=None)
    payload: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    notified: Mapped[int] = mapped_column(default=0)

    offer: Mapped["Offer"] = relationship(back_populates="events")


class MatchReview(Base):
    __tablename__ = "match_reviews"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    offer_id: Mapped[str] = mapped_column(String, ForeignKey("offers.id"), nullable=False)
    candidate_product_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("products.id"), default=None
    )
    suggested_products: Mapped[list | None] = mapped_column(JSON, default=None)
    best_confidence: Mapped[float | None] = mapped_column(default=None)
    reason: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[str] = mapped_column(String, default="pending")
    priority: Mapped[int] = mapped_column(default=0)
    decided_by: Mapped[str | None] = mapped_column(String, default=None)
    decided_at: Mapped[str | None] = mapped_column(String, default=None)
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class MatchDecision(Base):
    __tablename__ = "match_decisions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    offer_id: Mapped[str | None] = mapped_column(String, ForeignKey("offers.id"), default=None)
    product_id: Mapped[str | None] = mapped_column(String, ForeignKey("products.id"), default=None)
    decision_type: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[float | None] = mapped_column(default=None)
    signals: Mapped[dict | None] = mapped_column(JSON, default=None)
    actor: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    undo_snapshot: Mapped[dict | None] = mapped_column(JSON, default=None)


class FxRate(Base):
    __tablename__ = "fx_rates"

    currency: Mapped[str] = mapped_column(String, primary_key=True)
    rate_to_pln: Mapped[float] = mapped_column(nullable=False)
    fetched_at: Mapped[str] = mapped_column(String, nullable=False)
    table_no: Mapped[str | None] = mapped_column(String, default=None)
