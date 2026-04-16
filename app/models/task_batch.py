import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.statuses import TaskBatchStatus, enum_values


class TaskBatch(Base):
    __tablename__ = "task_batches"
    __table_args__ = (
        CheckConstraint(
            f"status IN {enum_values(TaskBatchStatus)}",
            name="ck_task_batches_status",
        ),
        UniqueConstraint("task_id", "batch_no", name="uq_task_batches_task_batch_no"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("trend_tasks.id"), index=True, nullable=False)
    batch_no: Mapped[int] = mapped_column(Integer, nullable=False)
    keywords: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    task = relationship("TrendTask", back_populates="batches")
    payloads = relationship("BatchPayload", back_populates="batch")
    effective_keywords = relationship("EffectiveKeyword", back_populates="batch")
    related_queries = relationship("TrendRelatedQuery", back_populates="batch")
