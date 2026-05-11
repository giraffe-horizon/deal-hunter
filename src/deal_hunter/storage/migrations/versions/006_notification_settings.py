"""Add offers.muted_until + alert_queue.deal_id, backfill deal_id from payload JSON.

Revision ID: 006
Revises: 005
Create Date: 2026-05-11
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("offers") as b:
        b.add_column(sa.Column("muted_until", sa.String(), nullable=True))
    op.create_index("ix_offers_muted_until", "offers", ["muted_until"])

    with op.batch_alter_table("alert_queue") as b:
        b.add_column(sa.Column("deal_id", sa.String(), nullable=True))
    op.create_index("ix_alert_queue_deal_id", "alert_queue", ["deal_id"])

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, payload FROM alert_queue")).fetchall()
    for row in rows:
        try:
            payload = json.loads(row[1])
        except (TypeError, ValueError):
            continue
        deal_id = payload.get("deal_id") if isinstance(payload, dict) else None
        if deal_id:
            conn.execute(
                sa.text("UPDATE alert_queue SET deal_id = :did WHERE id = :id"),
                {"did": deal_id, "id": row[0]},
            )


def downgrade() -> None:
    op.drop_index("ix_alert_queue_deal_id", table_name="alert_queue")
    with op.batch_alter_table("alert_queue") as b:
        b.drop_column("deal_id")
    op.drop_index("ix_offers_muted_until", table_name="offers")
    with op.batch_alter_table("offers") as b:
        b.drop_column("muted_until")
