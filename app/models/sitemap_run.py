import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.statuses import SitemapRunStatus, SitemapTriggerMode, enum_values


class SitemapRun(Base):
    __tablename__ = "sitemap_runs"
    __table_args__ = (
        CheckConstraint(
            f"trigger_mode IN {enum_values(SitemapTriggerMode)}",
            name="ck_sitemap_runs_trigger_mode",
        ),
        CheckConstraint(
            f"status IN {enum_values(SitemapRunStatus)}",
            name="ck_sitemap_runs_status",
        ),
        Index("ix_sitemap_runs_monitor_created_at", "monitor_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    monitor_id: Mapped[str] = mapped_column(String(36), ForeignKey("sitemap_monitors.id"), index=True, nullable=False)
    trigger_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="pending")
    result_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    snapshot_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_url_count: Mapped[int | None] = mapped_column(nullable=True)
    deleted_url_count: Mapped[int | None] = mapped_column(nullable=True)
    lastmod_changed_count: Mapped[int | None] = mapped_column(nullable=True)
    tracked_url_count: Mapped[int | None] = mapped_column(nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    monitor = relationship("SitemapMonitor", back_populates="runs")
