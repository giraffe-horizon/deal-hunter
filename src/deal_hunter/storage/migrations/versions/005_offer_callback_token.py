"""Add offers.callback_token column + index, backfill from id.

Revision ID: 005
Revises: 004
Create Date: 2026-04-24
"""

import hashlib
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("offers") as b:
        b.add_column(sa.Column("callback_token", sa.String(), nullable=True))

    op.create_index("ix_offers_callback_token", "offers", ["callback_token"])

    # Backfill token for existing rows.
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id FROM offers")).fetchall()
    for row in rows:
        token = hashlib.blake2s(row[0].encode("utf-8"), digest_size=8).hexdigest()
        conn.execute(
            sa.text("UPDATE offers SET callback_token = :tok WHERE id = :id"),
            {"tok": token, "id": row[0]},
        )


def downgrade() -> None:
    op.drop_index("ix_offers_callback_token", table_name="offers")
    with op.batch_alter_table("offers") as b:
        b.drop_column("callback_token")
