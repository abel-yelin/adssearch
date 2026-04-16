import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.statuses import TrendTaskStatus, enum_values


class TrendTask(Base):
    __tablename__ = "trend_tasks"
    __table_args__ = (
        CheckConstraint(
            f"status IN {enum_values(TrendTaskStatus)}",
            name="ck_trend_tasks_status",
        ),
        CheckConstraint("threshold >= 0", name="ck_trend_tasks_threshold_non_negative"),
        CheckConstraint("max_keywords > 0", name="ck_trend_tasks_max_keywords_positive"),
        CheckConstraint("batch_size > 0 AND batch_size <= 4", name="ck_trend_tasks_batch_size_range"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    base_keyword: Mapped[str] = mapped_column(Text, nullable=False)
    time_range: Mapped[str] = mapped_column(String(32), nullable=False)
    threshold: Mapped[int] = mapped_column(Integer, nullable=False)
    max_keywords: Mapped[int] = mapped_column(Integer, nullable=False)
    batch_size: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    geo: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    language: Mapped[str] = mapped_column(String(32), nullable=False, default="en-US")
    timezone_offset: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    seed_keywords: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    request_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    result_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    processed_keywords_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    effective_keywords_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_batch_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    batches = relationship("TaskBatch", back_populates="task")
    keywords = relationship("TaskKeyword", back_populates="task")
    effective_keywords = relationship("EffectiveKeyword", back_populates="task")
    related_queries = relationship("TrendRelatedQuery", back_populates="task")
