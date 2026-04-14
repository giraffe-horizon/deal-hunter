"""Rename deals -> offers, price_history -> price_points.

Revision ID: 003
Revises: 002
Create Date: 2026-04-13

Structural rename only. Column names, FK relationships, indices, and PK
values are preserved. Watchlist/feedback/seen_deals retain the column
name ``deal_id`` (it still holds the same offer id values).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_deals_profile_score")
    op.rename_table("deals", "offers")
    op.rename_table("price_history", "price_points")
    op.create_index("idx_offers_profile_score", "offers", ["profile", "score"])


def downgrade() -> None:
    op.drop_index("idx_offers_profile_score", table_name="offers")
    op.rename_table("price_points", "price_history")
    op.rename_table("offers", "deals")
    op.execute("CREATE INDEX IF NOT EXISTS idx_deals_profile_score ON deals (profile, score DESC)")
