from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.search_task import SearchTask


_UNSET = object()


class TaskRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_task(
        self,
        task_id: str,
        queue_job_id: str,
        domain: str,
        region: str,
        status: str,
        request_payload: dict,
        retry_count: int,
    ) -> SearchTask:
        task = SearchTask(
            task_id=task_id,
            queue_job_id=queue_job_id,
            domain=domain,
            region=region,
            status=status,
            request_payload=request_payload,
            retry_count=retry_count,
        )
        self.session.add(task)
        self.session.flush()
        return task

    def get_by_task_id(self, task_id: str) -> SearchTask | None:
        stmt = select(SearchTask).where(SearchTask.task_id == task_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def update_status(
        self,
        task_id: str,
        status: str,
        result_payload: dict | None = None,
        error_message=_UNSET,
        retry_count: int | None = None,
        started: bool = False,
        finished: bool = False,
    ) -> SearchTask | None:
        task = self.get_by_task_id(task_id)
        if task is None:
            return None

        now = datetime.now(UTC)
        task.status = status
        task.updated_at = now
        if result_payload is not None:
            task.result_payload = result_payload
            self._apply_result_projection(task, result_payload)
        if error_message is not _UNSET:
            task.error_message = error_message
        if retry_count is not None:
            task.retry_count = retry_count
        if started and task.started_at is None:
            task.started_at = now
        if finished:
            task.finished_at = now
        self.session.add(task)
        self.session.flush()
        return task

    @staticmethod
    def _apply_result_projection(task: SearchTask, result_payload: dict) -> None:
        data = result_payload.get("data") if isinstance(result_payload, dict) else None
        if not isinstance(data, dict):
            return
        advertisers = data.get("advertisers")
        task.has_ads = bool(data.get("has_ads")) if data.get("has_ads") is not None else None
        task.total_ads_found = int(data.get("total_ads_found")) if data.get("total_ads_found") is not None else None
        task.advertiser_count = len(advertisers) if isinstance(advertisers, list) else None
