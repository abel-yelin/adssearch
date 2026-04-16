"""baseline schema

Revision ID: 0001_baseline_schema
Revises:
Create Date: 2026-04-16 12:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_baseline_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "search_tasks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("queue_job_id", sa.String(length=64), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("region", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("result_payload", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("task_id"),
        sa.UniqueConstraint("queue_job_id"),
    )
    op.create_index("ix_search_tasks_task_id", "search_tasks", ["task_id"])
    op.create_index("ix_search_tasks_queue_job_id", "search_tasks", ["queue_job_id"])
    op.create_index("ix_search_tasks_domain", "search_tasks", ["domain"])
    op.create_index("ix_search_tasks_status", "search_tasks", ["status"])

    op.create_table(
        "trend_tasks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("base_keyword", sa.Text(), nullable=False),
        sa.Column("time_range", sa.String(length=32), nullable=False),
        sa.Column("threshold", sa.Integer(), nullable=False),
        sa.Column("max_keywords", sa.Integer(), nullable=False),
        sa.Column("geo", sa.String(length=32), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=False),
        sa.Column("timezone_offset", sa.Integer(), nullable=False),
        sa.Column("seed_keywords", sa.JSON(), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("result_payload", sa.JSON(), nullable=True),
        sa.Column("processed_keywords_count", sa.Integer(), nullable=False),
        sa.Column("effective_keywords_count", sa.Integer(), nullable=False),
        sa.Column("current_batch_no", sa.Integer(), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_trend_tasks_status", "trend_tasks", ["status"])

    op.create_table(
        "task_batches",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("task_id", sa.String(length=36), sa.ForeignKey("trend_tasks.id"), nullable=False),
        sa.Column("batch_no", sa.Integer(), nullable=False),
        sa.Column("keywords", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_task_batches_task_id", "task_batches", ["task_id"])
    op.create_index("ix_task_batches_status", "task_batches", ["status"])

    op.create_table(
        "task_keywords",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.String(length=36), sa.ForeignKey("trend_tasks.id"), nullable=False),
        sa.Column("keyword", sa.Text(), nullable=False),
        sa.Column("source_keyword", sa.Text(), nullable=True),
        sa.Column("source_type", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("is_effective", sa.Boolean(), nullable=False),
        sa.Column("skip_reason", sa.String(length=64), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("task_id", "keyword", name="uq_task_keywords_task_keyword"),
    )
    op.create_index("ix_task_keywords_task_id", "task_keywords", ["task_id"])
    op.create_index("ix_task_keywords_status", "task_keywords", ["status"])

    op.create_table(
        "effective_keywords",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.String(length=36), sa.ForeignKey("trend_tasks.id"), nullable=False),
        sa.Column("keyword", sa.Text(), nullable=False),
        sa.Column("source_batch_id", sa.String(length=36), sa.ForeignKey("task_batches.id"), nullable=False),
        sa.Column("score_percent", sa.Numeric(10, 2), nullable=False),
        sa.Column("first_five_all_zero", sa.Boolean(), nullable=False),
        sa.Column("last_five_avg", sa.Numeric(10, 2), nullable=False),
        sa.Column("base_last_five_avg", sa.Numeric(10, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("task_id", "keyword", name="uq_effective_keywords_task_keyword"),
    )
    op.create_index("ix_effective_keywords_task_id", "effective_keywords", ["task_id"])

    op.create_table(
        "batch_payloads",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("batch_id", sa.String(length=36), sa.ForeignKey("task_batches.id"), nullable=False),
        sa.Column("payload_type", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_batch_payloads_batch_id", "batch_payloads", ["batch_id"])

    op.create_table(
        "sitemap_monitors",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("site_url", sa.Text(), nullable=False),
        sa.Column("sitemap_url", sa.Text(), nullable=False),
        sa.Column("interval_minutes", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("latest_result", sa.JSON(), nullable=True),
        sa.Column("last_snapshot", sa.JSON(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_check_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_sitemap_monitors_status", "sitemap_monitors", ["status"])
    op.create_index("ix_sitemap_monitors_next_check_at", "sitemap_monitors", ["next_check_at"])

    op.create_table(
        "sitemap_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("monitor_id", sa.String(length=36), sa.ForeignKey("sitemap_monitors.id"), nullable=False),
        sa.Column("trigger_mode", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("result_payload", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_sitemap_runs_monitor_id", "sitemap_runs", ["monitor_id"])
    op.create_index("ix_sitemap_runs_status", "sitemap_runs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_sitemap_runs_status", table_name="sitemap_runs")
    op.drop_index("ix_sitemap_runs_monitor_id", table_name="sitemap_runs")
    op.drop_table("sitemap_runs")

    op.drop_index("ix_sitemap_monitors_next_check_at", table_name="sitemap_monitors")
    op.drop_index("ix_sitemap_monitors_status", table_name="sitemap_monitors")
    op.drop_table("sitemap_monitors")

    op.drop_index("ix_batch_payloads_batch_id", table_name="batch_payloads")
    op.drop_table("batch_payloads")

    op.drop_index("ix_effective_keywords_task_id", table_name="effective_keywords")
    op.drop_table("effective_keywords")

    op.drop_index("ix_task_keywords_status", table_name="task_keywords")
    op.drop_index("ix_task_keywords_task_id", table_name="task_keywords")
    op.drop_table("task_keywords")

    op.drop_index("ix_task_batches_status", table_name="task_batches")
    op.drop_index("ix_task_batches_task_id", table_name="task_batches")
    op.drop_table("task_batches")

    op.drop_index("ix_trend_tasks_status", table_name="trend_tasks")
    op.drop_table("trend_tasks")

    op.drop_index("ix_search_tasks_status", table_name="search_tasks")
    op.drop_index("ix_search_tasks_domain", table_name="search_tasks")
    op.drop_index("ix_search_tasks_queue_job_id", table_name="search_tasks")
    op.drop_index("ix_search_tasks_task_id", table_name="search_tasks")
    op.drop_table("search_tasks")
