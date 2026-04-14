"""Add seen_deals table for JSON state consolidation.

Revision ID: 002
Revises: 001
Create Date: 2026-04-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "seen_deals",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("deal_id", sa.Text, nullable=False),
        sa.Column("profile", sa.Text, nullable=False),
        sa.Column("dedup_key", sa.Text, nullable=False),
        sa.Column("first_seen_at", sa.Text, nullable=False),
    )
    op.create_index("idx_seen_deals_profile_deal", "seen_deals", ["profile", "deal_id"])


def downgrade() -> None:
    op.drop_index("idx_seen_deals_profile_deal", "seen_deals")
    op.drop_table("seen_deals")
