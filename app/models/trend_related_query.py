from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TrendRelatedQuery(Base):
    __tablename__ = "trend_related_queries"
    __table_args__ = (
        UniqueConstraint("batch_id", "source_keyword", "query", name="uq_trend_related_queries_batch_source_query"),
        Index("ix_trend_related_queries_query", "query"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("trend_tasks.id"), index=True, nullable=False)
    batch_id: Mapped[str] = mapped_column(String(36), ForeignKey("task_batches.id"), index=True, nullable=False)
    source_keyword: Mapped[str] = mapped_column(Text, nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    value_label: Mapped[str] = mapped_column(String(64), nullable=False)
    is_breakout: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    task = relationship("TrendTask", back_populates="related_queries")
    batch = relationship("TaskBatch", back_populates="related_queries")
