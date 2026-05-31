"""Add sent_notifications table for persistent dispatch history.

Revision ID: 007
Revises: 006
Create Date: 2026-05-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: str | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sent_notifications",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("alert_type", sa.String(), nullable=False),
        sa.Column("deal_id", sa.String(), nullable=True),
        sa.Column("profile", sa.String(), nullable=True),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("sent_at", sa.String(), nullable=False),
    )
    op.create_index(
        "ix_sent_notifications_deal_id_alert_type",
        "sent_notifications",
        ["deal_id", "alert_type", "sent_at"],
    )
    op.create_index(
        "ix_sent_notifications_sent_at",
        "sent_notifications",
        ["sent_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_sent_notifications_sent_at", table_name="sent_notifications")
    op.drop_index("ix_sent_notifications_deal_id_alert_type", table_name="sent_notifications")
    op.drop_table("sent_notifications")
