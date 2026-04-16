"""trend batch size

Revision ID: 0003_trend_batch_size
Revises: 0002_status_model_unification
Create Date: 2026-04-16 13:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003_trend_batch_size"
down_revision = "0002_status_model_unification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("trend_tasks") as batch_op:
        batch_op.add_column(sa.Column("batch_size", sa.Integer(), nullable=True, server_default="4"))

    op.execute("UPDATE trend_tasks SET batch_size = 4 WHERE batch_size IS NULL")

    with op.batch_alter_table("trend_tasks") as batch_op:
        batch_op.alter_column("batch_size", nullable=False, server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("trend_tasks") as batch_op:
        batch_op.drop_column("batch_size")
