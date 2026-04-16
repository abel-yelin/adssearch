"""status model unification

Revision ID: 0002_status_model_unification
Revises: 0001_baseline_schema
Create Date: 2026-04-16 12:30:00
"""

from __future__ import annotations

from alembic import op


revision = "0002_status_model_unification"
down_revision = "0001_baseline_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE search_tasks SET status = 'pending' WHERE status IN ('queued', 'scheduled', 'deferred')")
    op.execute("UPDATE search_tasks SET status = 'running' WHERE status = 'started'")
    op.execute("UPDATE search_tasks SET status = 'completed' WHERE status = 'finished'")
    op.execute("UPDATE search_tasks SET status = 'cancelled' WHERE status IN ('canceled', 'stopped')")
    op.execute("UPDATE trend_tasks SET status = 'cancelled' WHERE status = 'canceled'")
    op.execute("UPDATE sitemap_runs SET status = 'cancelled' WHERE status = 'canceled'")

    with op.batch_alter_table("search_tasks") as batch_op:
        batch_op.create_check_constraint(
            "ck_search_tasks_status",
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
        )

    with op.batch_alter_table("trend_tasks") as batch_op:
        batch_op.create_check_constraint(
            "ck_trend_tasks_status",
            "status IN ('pending', 'running', 'retrying', 'cooldown', 'completed', 'failed', 'cancelled')",
        )

    with op.batch_alter_table("task_batches") as batch_op:
        batch_op.create_check_constraint(
            "ck_task_batches_status",
            "status IN ('running', 'retrying', 'cooldown', 'succeeded', 'failed', 'cancelled')",
        )

    with op.batch_alter_table("task_keywords") as batch_op:
        batch_op.create_check_constraint(
            "ck_task_keywords_source_type",
            "source_type IN ('seed', 'related')",
        )
        batch_op.create_check_constraint(
            "ck_task_keywords_status",
            "status IN ('queued', 'running', 'processed', 'skipped')",
        )

    with op.batch_alter_table("sitemap_monitors") as batch_op:
        batch_op.create_check_constraint(
            "ck_sitemap_monitors_status",
            "status IN ('idle', 'queued', 'running', 'completed', 'failed', 'paused')",
        )

    with op.batch_alter_table("sitemap_runs") as batch_op:
        batch_op.create_check_constraint(
            "ck_sitemap_runs_trigger_mode",
            "trigger_mode IN ('manual', 'scheduled')",
        )
        batch_op.create_check_constraint(
            "ck_sitemap_runs_status",
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
        )


def downgrade() -> None:
    with op.batch_alter_table("sitemap_runs") as batch_op:
        batch_op.drop_constraint("ck_sitemap_runs_status", type_="check")
        batch_op.drop_constraint("ck_sitemap_runs_trigger_mode", type_="check")

    with op.batch_alter_table("sitemap_monitors") as batch_op:
        batch_op.drop_constraint("ck_sitemap_monitors_status", type_="check")

    with op.batch_alter_table("task_keywords") as batch_op:
        batch_op.drop_constraint("ck_task_keywords_status", type_="check")
        batch_op.drop_constraint("ck_task_keywords_source_type", type_="check")

    with op.batch_alter_table("task_batches") as batch_op:
        batch_op.drop_constraint("ck_task_batches_status", type_="check")

    with op.batch_alter_table("trend_tasks") as batch_op:
        batch_op.drop_constraint("ck_trend_tasks_status", type_="check")

    with op.batch_alter_table("search_tasks") as batch_op:
        batch_op.drop_constraint("ck_search_tasks_status", type_="check")

    op.execute("UPDATE sitemap_runs SET status = 'canceled' WHERE status = 'cancelled'")
    op.execute("UPDATE trend_tasks SET status = 'canceled' WHERE status = 'cancelled'")
    op.execute("UPDATE search_tasks SET status = 'canceled' WHERE status = 'cancelled'")
    op.execute("UPDATE search_tasks SET status = 'finished' WHERE status = 'completed'")
    op.execute("UPDATE search_tasks SET status = 'started' WHERE status = 'running'")
    op.execute("UPDATE search_tasks SET status = 'queued' WHERE status = 'pending'")
