"""structured query projections

Revision ID: 0004_structured_query_projections
Revises: 0003_trend_batch_size
Create Date: 2026-04-16 13:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0004_structured_query_projections"
down_revision = "0003_trend_batch_size"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("search_tasks") as batch_op:
        batch_op.add_column(sa.Column("has_ads", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("total_ads_found", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("advertiser_count", sa.Integer(), nullable=True))

    with op.batch_alter_table("sitemap_runs") as batch_op:
        batch_op.add_column(sa.Column("new_url_count", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("deleted_url_count", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("lastmod_changed_count", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("tracked_url_count", sa.Integer(), nullable=True))

    op.create_table(
        "trend_related_queries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.String(length=36), sa.ForeignKey("trend_tasks.id"), nullable=False),
        sa.Column("batch_id", sa.String(length=36), sa.ForeignKey("task_batches.id"), nullable=False),
        sa.Column("source_keyword", sa.Text(), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("value_label", sa.String(length=64), nullable=False),
        sa.Column("is_breakout", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("batch_id", "source_keyword", "query", name="uq_trend_related_queries_batch_source_query"),
    )
    op.create_index("ix_trend_related_queries_task_id", "trend_related_queries", ["task_id"])
    op.create_index("ix_trend_related_queries_batch_id", "trend_related_queries", ["batch_id"])


def downgrade() -> None:
    op.drop_index("ix_trend_related_queries_batch_id", table_name="trend_related_queries")
    op.drop_index("ix_trend_related_queries_task_id", table_name="trend_related_queries")
    op.drop_table("trend_related_queries")

    with op.batch_alter_table("sitemap_runs") as batch_op:
        batch_op.drop_column("tracked_url_count")
        batch_op.drop_column("lastmod_changed_count")
        batch_op.drop_column("deleted_url_count")
        batch_op.drop_column("new_url_count")

    with op.batch_alter_table("search_tasks") as batch_op:
        batch_op.drop_column("advertiser_count")
        batch_op.drop_column("total_ads_found")
        batch_op.drop_column("has_ads")
