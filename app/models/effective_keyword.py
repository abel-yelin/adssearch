from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EffectiveKeyword(Base):
    __tablename__ = "effective_keywords"
    __table_args__ = (UniqueConstraint("task_id", "keyword", name="uq_effective_keywords_task_keyword"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("trend_tasks.id"), index=True, nullable=False)
    keyword: Mapped[str] = mapped_column(Text, nullable=False)
    source_batch_id: Mapped[str] = mapped_column(String(36), ForeignKey("task_batches.id"), nullable=False)
    score_percent: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    first_five_all_zero: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_five_avg: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    base_last_five_avg: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
