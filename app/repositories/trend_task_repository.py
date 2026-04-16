from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.statuses import (
    TaskBatchStatus,
    TaskKeywordSourceType,
    TaskKeywordStatus,
    TrendTaskStatus,
)
from app.models.batch_payload import BatchPayload
from app.models.effective_keyword import EffectiveKeyword
from app.models.task_batch import TaskBatch
from app.models.task_keyword import TaskKeyword
from app.models.trend_related_query import TrendRelatedQuery
from app.models.trend_task import TrendTask


class TrendTaskRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_task(self, *, task_id: str, payload: dict) -> TrendTask:
        task = TrendTask(
            id=task_id,
            status=TrendTaskStatus.PENDING.value,
            base_keyword=payload["base_keyword"],
            time_range=payload["time_range"],
            threshold=payload["threshold"],
            max_keywords=payload["max_keywords"],
            batch_size=payload.get("batch_size", 4),
            geo=payload.get("geo", ""),
            language=payload.get("language", "en-US"),
            timezone_offset=payload.get("timezone_offset", 0),
            seed_keywords=payload["seed_keywords"],
            request_payload=payload,
        )
        self.session.add(task)
        self.session.flush()
        return task

    def get_task(self, task_id: str) -> TrendTask | None:
        stmt = select(TrendTask).where(TrendTask.id == task_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def set_task_status(
        self,
        task_id: str,
        status: str,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
        result_payload: dict | None = None,
        started: bool = False,
        finished: bool = False,
        increment_retry: bool = False,
    ) -> TrendTask | None:
        task = self.get_task(task_id)
        if task is None:
            return None

        now = datetime.now(UTC)
        task.status = status
        task.updated_at = now
        task.error_code = error_code
        task.error_message = error_message
        if result_payload is not None:
            task.result_payload = result_payload
        if started and task.started_at is None:
            task.started_at = now
        if finished:
            task.finished_at = now
        if increment_retry:
            task.retry_count += 1
        self.session.add(task)
        self.session.flush()
        return task

    def create_seed_keywords(self, task_id: str, keywords: list[str]) -> None:
        for keyword in keywords:
            self.add_keyword(
                task_id=task_id,
                keyword=keyword,
                source_keyword=None,
                source_type=TaskKeywordSourceType.SEED.value,
                status=TaskKeywordStatus.QUEUED.value,
            )

    def add_keyword(
        self,
        *,
        task_id: str,
        keyword: str,
        source_keyword: str | None,
        source_type: str,
        status: str,
        skip_reason: str | None = None,
    ) -> TaskKeyword | None:
        exists_stmt = select(TaskKeyword).where(TaskKeyword.task_id == task_id, TaskKeyword.keyword == keyword)
        existing = self.session.execute(exists_stmt).scalar_one_or_none()
        if existing is not None:
            return None
        keyword_row = TaskKeyword(
            task_id=task_id,
            keyword=keyword,
            source_keyword=source_keyword,
            source_type=source_type,
            status=status,
            skip_reason=skip_reason,
        )
        self.session.add(keyword_row)
        self.session.flush()
        return keyword_row

    def pick_next_keywords(self, task_id: str, limit: int = 4) -> list[TaskKeyword]:
        stmt = (
            select(TaskKeyword)
            .where(TaskKeyword.task_id == task_id, TaskKeyword.status == TaskKeywordStatus.QUEUED.value)
            .order_by(TaskKeyword.id.asc())
            .limit(limit)
        )
        rows = list(self.session.execute(stmt).scalars().all())
        now = datetime.now(UTC)
        for row in rows:
            row.status = TaskKeywordStatus.RUNNING.value
            row.updated_at = now
            self.session.add(row)
        self.session.flush()
        return rows

    def mark_keywords_processed(self, task_id: str, keywords: list[str], *, skipped: dict[str, str] | None = None) -> None:
        now = datetime.now(UTC)
        stmt = select(TaskKeyword).where(TaskKeyword.task_id == task_id, TaskKeyword.keyword.in_(keywords))
        rows = self.session.execute(stmt).scalars().all()
        skipped = skipped or {}
        for row in rows:
            row.status = TaskKeywordStatus.SKIPPED.value if row.keyword in skipped else TaskKeywordStatus.PROCESSED.value
            row.skip_reason = skipped.get(row.keyword)
            row.processed_at = now
            row.updated_at = now
            self.session.add(row)
        self.session.flush()

    def revert_keywords_to_queue(self, task_id: str, keywords: list[str]) -> None:
        stmt = select(TaskKeyword).where(TaskKeyword.task_id == task_id, TaskKeyword.keyword.in_(keywords))
        rows = self.session.execute(stmt).scalars().all()
        for row in rows:
            row.status = TaskKeywordStatus.QUEUED.value
            self.session.add(row)
        self.session.flush()

    def create_batch(self, task_id: str, batch_no: int, keywords: list[str]) -> TaskBatch:
        batch = TaskBatch(
            task_id=task_id,
            batch_no=batch_no,
            keywords=keywords,
            status=TaskBatchStatus.RUNNING.value,
            started_at=datetime.now(UTC),
        )
        self.session.add(batch)
        self.session.flush()
        return batch

    def update_batch_status(
        self,
        batch_id: str,
        status: str,
        *,
        retry_count: int | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        finished: bool = False,
    ) -> TaskBatch | None:
        stmt = select(TaskBatch).where(TaskBatch.id == batch_id)
        batch = self.session.execute(stmt).scalar_one_or_none()
        if batch is None:
            return None
        batch.status = status
        batch.error_code = error_code
        batch.error_message = error_message
        batch.updated_at = datetime.now(UTC)
        if retry_count is not None:
            batch.retry_count = retry_count
        if finished:
            batch.finished_at = datetime.now(UTC)
        self.session.add(batch)
        self.session.flush()
        return batch

    def save_payload(self, batch_id: str, payload_type: str, payload: dict) -> BatchPayload:
        payload_row = BatchPayload(batch_id=batch_id, payload_type=payload_type, payload=payload)
        self.session.add(payload_row)
        self.session.flush()
        return payload_row

    def save_related_query_rows(self, task_id: str, batch_id: str, rows: list[dict]) -> None:
        for row in rows:
            self.session.add(
                TrendRelatedQuery(
                    task_id=task_id,
                    batch_id=batch_id,
                    source_keyword=row["source_keyword"],
                    query=row["query"],
                    value_label=row["value_label"],
                    is_breakout=bool(row["is_breakout"]),
                )
            )
        self.session.flush()

    def add_effective_keyword(self, task_id: str, batch_id: str, keyword: str, metrics: dict) -> EffectiveKeyword | None:
        stmt = select(EffectiveKeyword).where(EffectiveKeyword.task_id == task_id, EffectiveKeyword.keyword == keyword)
        existing = self.session.execute(stmt).scalar_one_or_none()
        if existing is not None:
            return None

        keyword_stmt = select(TaskKeyword).where(TaskKeyword.task_id == task_id, TaskKeyword.keyword == keyword)
        keyword_row = self.session.execute(keyword_stmt).scalar_one_or_none()
        if keyword_row is not None:
            keyword_row.is_effective = True
            self.session.add(keyword_row)

        row = EffectiveKeyword(
            task_id=task_id,
            source_batch_id=batch_id,
            keyword=keyword,
            score_percent=metrics["score_percent"],
            first_five_all_zero=metrics["first_five_all_zero"],
            last_five_avg=metrics["last_five_avg"],
            base_last_five_avg=metrics["base_last_five_avg"],
        )
        self.session.add(row)
        self.session.flush()
        return row

    def refresh_task_counters(self, task_id: str) -> TrendTask | None:
        task = self.get_task(task_id)
        if task is None:
            return None

        processed_stmt = select(func.count()).select_from(TaskKeyword).where(
            TaskKeyword.task_id == task_id,
            TaskKeyword.status.in_((TaskKeywordStatus.PROCESSED.value, TaskKeywordStatus.SKIPPED.value)),
        )
        effective_stmt = select(func.count()).select_from(EffectiveKeyword).where(EffectiveKeyword.task_id == task_id)
        batch_stmt = select(func.max(TaskBatch.batch_no)).where(TaskBatch.task_id == task_id)

        task.processed_keywords_count = int(self.session.execute(processed_stmt).scalar() or 0)
        task.effective_keywords_count = int(self.session.execute(effective_stmt).scalar() or 0)
        task.current_batch_no = int(self.session.execute(batch_stmt).scalar() or 0)
        task.updated_at = datetime.now(UTC)
        self.session.add(task)
        self.session.flush()
        return task

    def list_effective_keywords(self, task_id: str, limit: int | None = None) -> list[EffectiveKeyword]:
        stmt = select(EffectiveKeyword).where(EffectiveKeyword.task_id == task_id).order_by(EffectiveKeyword.score_percent.desc())
        if limit:
            stmt = stmt.limit(limit)
        return list(self.session.execute(stmt).scalars().all())

    def list_keywords_by_status(self, task_id: str, status: str) -> list[TaskKeyword]:
        stmt = select(TaskKeyword).where(TaskKeyword.task_id == task_id, TaskKeyword.status == status).order_by(TaskKeyword.id.asc())
        return list(self.session.execute(stmt).scalars().all())

    def list_all_batches(self, task_id: str) -> list[TaskBatch]:
        stmt = select(TaskBatch).where(TaskBatch.task_id == task_id).order_by(TaskBatch.batch_no.asc())
        return list(self.session.execute(stmt).scalars().all())

    def list_batch_payloads(self, batch_id: str) -> list[BatchPayload]:
        stmt = select(BatchPayload).where(BatchPayload.batch_id == batch_id).order_by(BatchPayload.id.asc())
        return list(self.session.execute(stmt).scalars().all())
