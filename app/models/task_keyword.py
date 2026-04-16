from datetime import UTC, datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.statuses import TaskKeywordSourceType, TaskKeywordStatus, enum_values


class TaskKeyword(Base):
    __tablename__ = "task_keywords"
    __table_args__ = (
        UniqueConstraint("task_id", "keyword", name="uq_task_keywords_task_keyword"),
        CheckConstraint(
            f"source_type IN {enum_values(TaskKeywordSourceType)}",
            name="ck_task_keywords_source_type",
        ),
        CheckConstraint(
            f"status IN {enum_values(TaskKeywordStatus)}",
            name="ck_task_keywords_status",
        ),
        Index("ix_task_keywords_task_status_id", "task_id", "status", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("trend_tasks.id"), index=True, nullable=False)
    keyword: Mapped[str] = mapped_column(Text, nullable=False)
    source_keyword: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    is_effective: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    skip_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    task = relationship("TrendTask", back_populates="keywords")
