"""Phase A2 — column renames on offers/price_points, additive columns, new tables.

Revision ID: 004
Revises: 003
Create Date: 2026-04-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- offers: column renames + additive columns ------------------------
    with op.batch_alter_table("offers") as b:
        b.alter_column("title", new_column_name="raw_title")
        b.alter_column("price", new_column_name="current_price_pln")
        b.alter_column("link", new_column_name="url")
        b.alter_column("first_seen", new_column_name="first_seen_at")
        b.alter_column("last_seen", new_column_name="last_seen_at")
        b.add_column(sa.Column("product_id", sa.String(), nullable=True))
        b.add_column(sa.Column("source_native_id", sa.String(), nullable=True))
        b.add_column(sa.Column("current_price_original", sa.Integer(), nullable=True))
        b.add_column(
            sa.Column(
                "currency_original",
                sa.String(),
                nullable=False,
                server_default="PLN",
            )
        )
        b.add_column(sa.Column("fx_rate_used", sa.Float(), nullable=True))
        b.add_column(sa.Column("availability", sa.String(), nullable=True))
        b.add_column(sa.Column("attributes_hint", sa.JSON(), nullable=True))
        b.add_column(
            sa.Column(
                "is_active",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )

    # --- price_points: column renames + additive columns ------------------
    with op.batch_alter_table("price_points") as b:
        b.alter_column("deal_id", new_column_name="offer_id")
        b.alter_column("price", new_column_name="price_pln")
        b.add_column(sa.Column("product_id", sa.String(), nullable=True))
        b.add_column(sa.Column("price_original", sa.Integer(), nullable=True))
        b.add_column(
            sa.Column(
                "currency_original",
                sa.String(),
                nullable=False,
                server_default="PLN",
            )
        )
        b.add_column(sa.Column("fx_rate_used", sa.Float(), nullable=True))
        b.add_column(sa.Column("availability", sa.String(), nullable=True))

    # --- backfill offers.source_native_id from id (split on first ':') ----
    op.execute(
        "UPDATE offers SET source_native_id = substr(id, instr(id, ':') + 1)"
        " WHERE source_native_id IS NULL"
    )

    # --- new tables -------------------------------------------------------
    op.create_table(
        "products",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("canonical_title", sa.Text(), nullable=False),
        sa.Column("brand", sa.String(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("canonical_image_url", sa.Text(), nullable=True),
        sa.Column("review_status", sa.String(), nullable=False, server_default="auto"),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("merged_from", sa.JSON(), nullable=True),
        sa.Column("archived", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
    )
    op.create_index("ix_products_brand_model", "products", ["brand", "model"])
    op.create_index("ix_products_category", "products", ["category"])
    op.create_index("ix_products_archived_updated", "products", ["archived", "updated_at"])

    op.create_table(
        "product_aliases",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "product_id",
            sa.String(),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("identifier_type", sa.String(), nullable=False),
        sa.Column("identifier_value", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.UniqueConstraint(
            "identifier_type",
            "identifier_value",
            "source",
            name="uq_alias_type_value_source",
        ),
    )
    op.create_index("ix_aliases_product", "product_aliases", ["product_id"])

    op.create_table(
        "offer_payload_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "offer_id",
            sa.String(),
            sa.ForeignKey("offers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("captured_at", sa.String(), nullable=False),
    )
    op.create_index(
        "ix_payload_offer_captured",
        "offer_payload_history",
        ["offer_id", "captured_at"],
    )

    op.create_table(
        "deal_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "offer_id",
            sa.String(),
            sa.ForeignKey("offers.id"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sa.String(),
            sa.ForeignKey("products.id"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("price_at_event", sa.Integer(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("notified", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_events_offer_created", "deal_events", ["offer_id", "created_at"])
    op.create_index("ix_events_product_created", "deal_events", ["product_id", "created_at"])
    op.create_index("ix_events_type_created", "deal_events", ["event_type", "created_at"])
    op.create_index("ix_events_notified", "deal_events", ["notified"])

    op.create_table(
        "match_reviews",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "offer_id",
            sa.String(),
            sa.ForeignKey("offers.id"),
            nullable=False,
        ),
        sa.Column(
            "candidate_product_id",
            sa.String(),
            sa.ForeignKey("products.id"),
            nullable=True,
        ),
        sa.Column("suggested_products", sa.JSON(), nullable=True),
        sa.Column("best_confidence", sa.Float(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("decided_by", sa.String(), nullable=True),
        sa.Column("decided_at", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
    )
    op.create_index("ix_reviews_status_priority", "match_reviews", ["status", "priority"])
    op.create_index("ix_reviews_offer", "match_reviews", ["offer_id"])

    op.create_table(
        "match_decisions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("offer_id", sa.String(), sa.ForeignKey("offers.id"), nullable=True),
        sa.Column(
            "product_id",
            sa.String(),
            sa.ForeignKey("products.id"),
            nullable=True,
        ),
        sa.Column("decision_type", sa.String(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("signals", sa.JSON(), nullable=True),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("undo_snapshot", sa.JSON(), nullable=True),
    )
    op.create_index("ix_decisions_offer", "match_decisions", ["offer_id"])
    op.create_index("ix_decisions_product", "match_decisions", ["product_id"])
    op.create_index("ix_decisions_created", "match_decisions", ["created_at"])

    op.create_table(
        "fx_rates",
        sa.Column("currency", sa.String(), primary_key=True),
        sa.Column("rate_to_pln", sa.Float(), nullable=False),
        sa.Column("fetched_at", sa.String(), nullable=False),
        sa.Column("table_no", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("fx_rates")
    op.drop_index("ix_decisions_created", table_name="match_decisions")
    op.drop_index("ix_decisions_product", table_name="match_decisions")
    op.drop_index("ix_decisions_offer", table_name="match_decisions")
    op.drop_table("match_decisions")
    op.drop_index("ix_reviews_offer", table_name="match_reviews")
    op.drop_index("ix_reviews_status_priority", table_name="match_reviews")
    op.drop_table("match_reviews")
    op.drop_index("ix_events_notified", table_name="deal_events")
    op.drop_index("ix_events_type_created", table_name="deal_events")
    op.drop_index("ix_events_product_created", table_name="deal_events")
    op.drop_index("ix_events_offer_created", table_name="deal_events")
    op.drop_table("deal_events")
    op.drop_index("ix_payload_offer_captured", table_name="offer_payload_history")
    op.drop_table("offer_payload_history")
    op.drop_index("ix_aliases_product", table_name="product_aliases")
    op.drop_table("product_aliases")
    op.drop_index("ix_products_archived_updated", table_name="products")
    op.drop_index("ix_products_category", table_name="products")
    op.drop_index("ix_products_brand_model", table_name="products")
    op.drop_table("products")

    with op.batch_alter_table("price_points") as b:
        b.drop_column("availability")
        b.drop_column("fx_rate_used")
        b.drop_column("currency_original")
        b.drop_column("price_original")
        b.drop_column("product_id")
        b.alter_column("price_pln", new_column_name="price")
        b.alter_column("offer_id", new_column_name="deal_id")

    with op.batch_alter_table("offers") as b:
        b.drop_column("is_active")
        b.drop_column("attributes_hint")
        b.drop_column("availability")
        b.drop_column("fx_rate_used")
        b.drop_column("currency_original")
        b.drop_column("current_price_original")
        b.drop_column("source_native_id")
        b.drop_column("product_id")
        b.alter_column("last_seen_at", new_column_name="last_seen")
        b.alter_column("first_seen_at", new_column_name="first_seen")
        b.alter_column("url", new_column_name="link")
        b.alter_column("current_price_pln", new_column_name="price")
        b.alter_column("raw_title", new_column_name="title")
