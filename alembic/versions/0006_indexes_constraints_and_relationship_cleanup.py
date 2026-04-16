"""indexes constraints and cleanup

Revision ID: 0006_indexes_constraints_and_relationship_cleanup
Revises: 0005_sitemap_snapshot_decoupling
Create Date: 2026-04-16 14:30:00
"""

from __future__ import annotations

from alembic import op


revision = "0006_indexes_constraints_and_relationship_cleanup"
down_revision = "0005_sitemap_snapshot_decoupling"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("trend_tasks") as batch_op:
        batch_op.create_check_constraint("ck_trend_tasks_threshold_non_negative", "threshold >= 0")
        batch_op.create_check_constraint("ck_trend_tasks_max_keywords_positive", "max_keywords > 0")
        batch_op.create_check_constraint("ck_trend_tasks_batch_size_range", "batch_size > 0 AND batch_size <= 4")

    with op.batch_alter_table("sitemap_monitors") as batch_op:
        batch_op.create_check_constraint("ck_sitemap_monitors_interval_positive", "interval_minutes > 0")

    with op.batch_alter_table("task_batches") as batch_op:
        batch_op.create_unique_constraint("uq_task_batches_task_batch_no", ["task_id", "batch_no"])

    op.create_index("ix_search_tasks_status_created_at", "search_tasks", ["status", "created_at"])
    op.create_index("ix_search_tasks_domain_created_at", "search_tasks", ["domain", "created_at"])
    op.create_index("ix_task_keywords_task_status_id", "task_keywords", ["task_id", "status", "id"])
    op.create_index("ix_effective_keywords_task_score_percent", "effective_keywords", ["task_id", "score_percent"])
    op.create_index("ix_batch_payloads_batch_payload_type", "batch_payloads", ["batch_id", "payload_type"])
    op.create_index("ix_trend_related_queries_query", "trend_related_queries", ["query"])
    op.create_index("ix_sitemap_monitors_enabled_next_check_at", "sitemap_monitors", ["enabled", "next_check_at"])
    op.create_index("ix_sitemap_runs_monitor_created_at", "sitemap_runs", ["monitor_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_sitemap_runs_monitor_created_at", table_name="sitemap_runs")
    op.drop_index("ix_sitemap_monitors_enabled_next_check_at", table_name="sitemap_monitors")
    op.drop_index("ix_trend_related_queries_query", table_name="trend_related_queries")
    op.drop_index("ix_batch_payloads_batch_payload_type", table_name="batch_payloads")
    op.drop_index("ix_effective_keywords_task_score_percent", table_name="effective_keywords")
    op.drop_index("ix_task_keywords_task_status_id", table_name="task_keywords")
    op.drop_index("ix_search_tasks_domain_created_at", table_name="search_tasks")
    op.drop_index("ix_search_tasks_status_created_at", table_name="search_tasks")

    with op.batch_alter_table("task_batches") as batch_op:
        batch_op.drop_constraint("uq_task_batches_task_batch_no", type_="unique")

    with op.batch_alter_table("sitemap_monitors") as batch_op:
        batch_op.drop_constraint("ck_sitemap_monitors_interval_positive", type_="check")

    with op.batch_alter_table("trend_tasks") as batch_op:
        batch_op.drop_constraint("ck_trend_tasks_batch_size_range", type_="check")
        batch_op.drop_constraint("ck_trend_tasks_max_keywords_positive", type_="check")
        batch_op.drop_constraint("ck_trend_tasks_threshold_non_negative", type_="check")
