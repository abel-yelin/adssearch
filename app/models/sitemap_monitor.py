import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.statuses import SitemapMonitorStatus, enum_values


class SitemapMonitor(Base):
    __tablename__ = "sitemap_monitors"
    __table_args__ = (
        CheckConstraint(
            f"status IN {enum_values(SitemapMonitorStatus)}",
            name="ck_sitemap_monitors_status",
        ),
        CheckConstraint("interval_minutes > 0", name="ck_sitemap_monitors_interval_positive"),
        Index("ix_sitemap_monitors_enabled_next_check_at", "enabled", "next_check_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    site_url: Mapped[str] = mapped_column(Text, nullable=False)
    sitemap_url: Mapped[str] = mapped_column(Text, nullable=False)
    interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="idle")
    request_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    latest_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True, nullable=True)
    runs = relationship("SitemapRun", back_populates="monitor")
