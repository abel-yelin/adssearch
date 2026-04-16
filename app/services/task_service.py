import uuid

from rq.exceptions import InvalidJobOperation, NoSuchJobError

from app.db.session import get_db_session
from app.models.statuses import TrendTaskStatus
from app.repositories.trend_task_repository import TrendTaskRepository
from app.schemas.task import (
    TrendTaskActionResponse,
    TrendTaskCreateRequest,
    TrendTaskCreateResponse,
    TrendTaskExportResponse,
    TrendTaskStatusResponse,
    TrendTaskSummaryItem,
    TrendTaskSummaryResponse,
)
from app.services.queue_service import TaskQueueService
from app.utils.keyword_filters import normalize_keyword


class TaskService:
    def __init__(self, queue_service: TaskQueueService):
        self.queue_service = queue_service

    def create_task(self, request: TrendTaskCreateRequest) -> TrendTaskCreateResponse:
        task_id = str(uuid.uuid4())
        payload = request.model_dump()
        payload["base_keyword"] = normalize_keyword(payload["base_keyword"])
        payload["seed_keywords"] = list(
            dict.fromkeys(
                normalize_keyword(keyword)
                for keyword in payload["seed_keywords"]
                if normalize_keyword(keyword) and normalize_keyword(keyword).lower() != payload["base_keyword"].lower()
            )
        )
        if not payload["seed_keywords"]:
            raise ValueError("At least one valid seed keyword is required after normalization.")
        with get_db_session() as session:
            repo = TrendTaskRepository(session)
            repo.create_task(task_id=task_id, payload=payload)
            repo.create_seed_keywords(task_id, payload["seed_keywords"])

        self.queue_service.enqueue("app.tasks.trend_tasks.run_trend_task", payload, job_id=task_id)
        return TrendTaskCreateResponse(task_id=task_id, status=TrendTaskStatus.PENDING)

    def get_task_status(self, task_id: str) -> TrendTaskStatusResponse:
        with get_db_session() as session:
            repo = TrendTaskRepository(session)
            task = repo.get_task(task_id)
        if task is None:
            raise ValueError(f"Task '{task_id}' not found.")

        return TrendTaskStatusResponse(
            task_id=task.id,
            status=task.status,
            base_keyword=task.base_keyword,
            seed_keywords=task.seed_keywords,
            time_range=task.time_range,
            threshold=task.threshold,
            max_keywords=task.max_keywords,
            batch_size=task.batch_size,
            processed_keywords_count=task.processed_keywords_count,
            effective_keywords_count=task.effective_keywords_count,
            current_batch_no=task.current_batch_no,
            retries=task.retry_count,
            recent_error=task.error_message,
            error_code=task.error_code,
            result=task.result_payload,
            updated_at=task.updated_at,
        )

    def get_task_summary(self, task_id: str) -> TrendTaskSummaryResponse:
        with get_db_session() as session:
            repo = TrendTaskRepository(session)
            task = repo.get_task(task_id)
            if task is None:
                raise ValueError(f"Task '{task_id}' not found.")
            effective_keywords = repo.list_effective_keywords(task_id, limit=10)
            batch_no_map = {batch.id: batch.batch_no for batch in repo.list_all_batches(task_id)}

        return TrendTaskSummaryResponse(
            task_id=task.id,
            status=task.status,
            processed_keywords_count=task.processed_keywords_count,
            effective_keywords_count=task.effective_keywords_count,
            current_batch_no=task.current_batch_no,
            top_effective_keywords=[
                TrendTaskSummaryItem(
                    keyword=item.keyword,
                    score_percent=float(item.score_percent),
                    source_batch_no=batch_no_map.get(item.source_batch_id, 0),
                )
                for item in effective_keywords
            ],
            updated_at=task.updated_at,
        )

    def export_task(self, task_id: str) -> TrendTaskExportResponse:
        with get_db_session() as session:
            repo = TrendTaskRepository(session)
            task = repo.get_task(task_id)
            if task is None:
                raise ValueError(f"Task '{task_id}' not found.")

            effective_keywords = repo.list_effective_keywords(task_id)
            processed_keywords = repo.list_keywords_by_status(task_id, "processed")
            pending_keywords = repo.list_keywords_by_status(task_id, "queued")
            skipped_keywords = repo.list_keywords_by_status(task_id, "skipped")
            batches = repo.list_all_batches(task_id)

            all_captured_data = []
            for batch in batches:
                payloads = repo.list_batch_payloads(batch.id)
                all_captured_data.append(
                    {
                        "batch_no": batch.batch_no,
                        "keywords": batch.keywords,
                        "status": batch.status,
                        "retry_count": batch.retry_count,
                        "captured_data": {
                            payload.payload_type: payload.payload for payload in payloads
                        },
                    }
                )

        return TrendTaskExportResponse(
            task_id=task.id,
            base_keyword=task.base_keyword,
            time_range=task.time_range,
            threshold=task.threshold,
            max_keywords=task.max_keywords,
            batch_size=task.batch_size,
            status=task.status,
            effective_new_words=[
                {
                    "keyword": item.keyword,
                    "score_percent": float(item.score_percent),
                    "first_five_all_zero": item.first_five_all_zero,
                    "last_five_avg": float(item.last_five_avg),
                    "base_last_five_avg": float(item.base_last_five_avg),
                }
                for item in effective_keywords
            ],
            processed_keywords=[item.keyword for item in processed_keywords],
            pending_keywords=[item.keyword for item in pending_keywords],
            skipped_keywords=[
                {"keyword": item.keyword, "skip_reason": item.skip_reason}
                for item in skipped_keywords
            ],
            all_captured_data=all_captured_data,
            statistics={
                "processed_keywords_count": task.processed_keywords_count,
                "effective_keywords_count": task.effective_keywords_count,
                "current_batch_no": task.current_batch_no,
                "retry_count": task.retry_count,
            },
        )

    def cancel_task(self, task_id: str) -> TrendTaskActionResponse:
        with get_db_session() as session:
            repo = TrendTaskRepository(session)
            task = repo.get_task(task_id)
            if task is None:
                raise ValueError(f"Task '{task_id}' not found.")
            if task.status in {
                TrendTaskStatus.COMPLETED.value,
                TrendTaskStatus.FAILED.value,
                TrendTaskStatus.CANCELLED.value,
            }:
                return TrendTaskActionResponse(task_id=task_id, status=task.status, message="Task is already finalized.")
            repo.set_task_status(task_id, TrendTaskStatus.CANCELLED.value, error_code=None, error_message=None, finished=True)

        job = self._safe_fetch_job(task_id)
        if job is not None:
            status = job.get_status(refresh=True)
            if status not in {"finished", "failed", "canceled", "stopped"}:
                try:
                    job.cancel()
                except Exception:
                    pass
        return TrendTaskActionResponse(task_id=task_id, status=TrendTaskStatus.CANCELLED, message="Task cancelled successfully.")

    def retry_task(self, task_id: str) -> TrendTaskActionResponse:
        with get_db_session() as session:
            repo = TrendTaskRepository(session)
            task = repo.get_task(task_id)
            if task is None:
                raise ValueError(f"Task '{task_id}' not found.")
            if task.status not in {TrendTaskStatus.FAILED.value, TrendTaskStatus.CANCELLED.value}:
                return TrendTaskActionResponse(
                    task_id=task_id,
                    status=task.status,
                    message=f"Task cannot be retried from status '{task.status}'.",
                )
            payload = task.request_payload

        new_task_id = str(uuid.uuid4())
        with get_db_session() as session:
            repo = TrendTaskRepository(session)
            repo.create_task(task_id=new_task_id, payload=payload)
            repo.create_seed_keywords(new_task_id, payload["seed_keywords"])

        self.queue_service.enqueue("app.tasks.trend_tasks.run_trend_task", payload, job_id=new_task_id)
        return TrendTaskActionResponse(
            task_id=task_id,
            new_task_id=new_task_id,
            status=TrendTaskStatus.PENDING,
            message="Task retried successfully.",
        )

    def _safe_fetch_job(self, task_id: str):
        try:
            return self.queue_service.fetch_job(task_id)
        except (NoSuchJobError, InvalidJobOperation):
            return None
