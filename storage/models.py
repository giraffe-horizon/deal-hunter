"""SQLAlchemy ORM models for Deal Hunter."""

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Deal(Base):
    __tablename__ = "deals"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[int | None] = mapped_column(default=None)
    link: Mapped[str | None] = mapped_column(Text, default=None)
    source: Mapped[str | None] = mapped_column(String, default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    image_url: Mapped[str | None] = mapped_column(Text, default=None)
    profile: Mapped[str | None] = mapped_column(String, default=None)
    score: Mapped[int | None] = mapped_column(default=None)
    category: Mapped[str | None] = mapped_column(String, default=None)
    status: Mapped[str] = mapped_column(String, default="active")
    first_seen: Mapped[str | None] = mapped_column(String, default=None)
    last_seen: Mapped[str | None] = mapped_column(String, default=None)

    prices: Mapped[list["PriceHistory"]] = relationship(back_populates="deal")
    feedback_entries: Mapped[list["Feedback"]] = relationship(back_populates="deal")
    watchlist_entry: Mapped["WatchlistItem | None"] = relationship(back_populates="deal")

    __table_args__ = (Index("idx_deals_profile_score", "profile", "score"),)


class PriceHistory(Base):
    __tablename__ = "price_history"

    deal_id: Mapped[str] = mapped_column(String, ForeignKey("deals.id"), primary_key=True)
    price: Mapped[int] = mapped_column(nullable=False)
    recorded_at: Mapped[str] = mapped_column(String, primary_key=True)

    deal: Mapped["Deal"] = relationship(back_populates="prices")


class Feedback(Base):
    __tablename__ = "feedback"

    deal_id: Mapped[str] = mapped_column(String, ForeignKey("deals.id"), primary_key=True)
    action: Mapped[str | None] = mapped_column(String, default=None)
    created_at: Mapped[str] = mapped_column(String, primary_key=True)

    deal: Mapped["Deal"] = relationship(back_populates="feedback_entries")


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
        String, ForeignKey("deals.id"), nullable=False, unique=True
    )
    target_price: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    triggered_at: Mapped[str | None] = mapped_column(String, default=None)

    deal: Mapped["Deal"] = relationship(back_populates="watchlist_entry")


class SeenDeal(Base):
    """Replaces JSON state files for seen-deal tracking."""

    __tablename__ = "seen_deals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    deal_id: Mapped[str] = mapped_column(String, nullable=False)
    profile: Mapped[str] = mapped_column(String, nullable=False)
    dedup_key: Mapped[str] = mapped_column(String, nullable=False)
    first_seen_at: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (Index("idx_seen_deals_profile_deal", "profile", "deal_id"),)
