"""sitemap snapshot decoupling

Revision ID: 0005_sitemap_snapshot_decoupling
Revises: 0004_structured_query_projections
Create Date: 2026-04-16 14:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0005_sitemap_snapshot_decoupling"
down_revision = "0004_structured_query_projections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("sitemap_runs") as batch_op:
        batch_op.add_column(sa.Column("snapshot_payload", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("sitemap_runs") as batch_op:
        batch_op.drop_column("snapshot_payload")
