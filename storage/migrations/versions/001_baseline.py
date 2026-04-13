"""Baseline — existing schema (deals, price_history, feedback, alert_queue, watchlist).

Revision ID: 001
Revises: None
Create Date: 2026-04-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "deals",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("price", sa.Integer),
        sa.Column("link", sa.Text),
        sa.Column("source", sa.Text),
        sa.Column("description", sa.Text),
        sa.Column("image_url", sa.Text),
        sa.Column("profile", sa.Text),
        sa.Column("score", sa.Integer),
        sa.Column("category", sa.Text),
        sa.Column("first_seen", sa.Text),
        sa.Column("last_seen", sa.Text),
        sa.Column("status", sa.Text, server_default="active"),
    )
    op.create_index("idx_deals_profile_score", "deals", ["profile", "score"])

    op.create_table(
        "price_history",
        sa.Column("deal_id", sa.Text, sa.ForeignKey("deals.id")),
        sa.Column("price", sa.Integer, nullable=False),
        sa.Column("recorded_at", sa.Text),
        sa.PrimaryKeyConstraint("deal_id", "recorded_at"),
    )

    op.create_table(
        "feedback",
        sa.Column("deal_id", sa.Text, sa.ForeignKey("deals.id")),
        sa.Column("action", sa.Text),
        sa.Column("created_at", sa.Text),
    )

    op.create_table(
        "alert_queue",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("profile", sa.Text, nullable=False),
        sa.Column("alert_type", sa.Text, nullable=False),
        sa.Column("payload", sa.Text, nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("sent_at", sa.Text),
    )

    op.create_table(
        "watchlist",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("deal_id", sa.Text, nullable=False, unique=True),
        sa.Column("target_price", sa.Integer, nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("triggered_at", sa.Text),
    )


def downgrade() -> None:
    op.drop_table("watchlist")
    op.drop_table("alert_queue")
    op.drop_table("feedback")
    op.drop_table("price_history")
    op.drop_index("idx_deals_profile_score", "deals")
    op.drop_table("deals")
