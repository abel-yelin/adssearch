import uuid

from rq.exceptions import InvalidJobOperation, NoSuchJobError

from app.db.session import get_db_session
from app.repositories.task_repository import TaskRepository
from app.schemas.search import (
    SearchRequest,
    SearchTaskStatusResponse,
    SearchTaskSubmitResponse,
    TaskActionResponse,
)
from app.services.queue_service import TaskQueueService


class AdsTaskService:
    def __init__(self, queue_service: TaskQueueService):
        self.queue_service = queue_service

    def submit_search(self, request: SearchRequest) -> SearchTaskSubmitResponse:
        task_id = str(uuid.uuid4())
        with get_db_session() as session:
            repo = TaskRepository(session)
            repo.create_task(
                task_id=task_id,
                queue_job_id=task_id,
                domain=request.domain,
                region=request.region,
                status="queued",
                request_payload=request.model_dump(),
                retry_count=self.queue_service.settings.queue_default_retry_count,
            )
        self.queue_service.enqueue(
            "app.tasks.search_tasks.run_search_task",
            request.model_dump(),
            job_id=task_id,
        )
        return SearchTaskSubmitResponse(
            success=True,
            task_id=task_id,
            status="queued",
            message="Search task submitted successfully.",
        )

    def get_task_status(self, task_id: str) -> SearchTaskStatusResponse:
        with get_db_session() as session:
            repo = TaskRepository(session)
            task = repo.get_by_task_id(task_id)
        if task is None:
            return SearchTaskStatusResponse(
                success=False,
                task_id=task_id,
                status="unknown",
                error="Task not found.",
            )

        job = self._safe_fetch_job(task_id)
        status = task.status
        retries_left = task.retry_count
        result = task.result_payload
        error = task.error_message
        if job is not None:
            job_status = job.get_status(refresh=True)
            if task.status in {"queued", "started"}:
                status = job_status
        return SearchTaskStatusResponse(
            success=status != "failed",
            task_id=task_id,
            status=status,
            result=result,
            error=error,
            retries_left=retries_left,
        )

    def cancel_task(self, task_id: str) -> TaskActionResponse:
        job = self._safe_fetch_job(task_id)
        if job is None:
            return TaskActionResponse(
                success=False,
                task_id=task_id,
                status="unknown",
                message="Task not found.",
            )

        status = job.get_status(refresh=True)
        if status in {"finished", "failed", "canceled", "stopped"}:
            return TaskActionResponse(
                success=False,
                task_id=task_id,
                status=status,
                message=f"Task cannot be canceled from status '{status}'.",
            )

        if status == "started":
            self.queue_service.stop_job(task_id)
            with get_db_session() as session:
                TaskRepository(session).update_status(task_id, status="stopped", finished=True)
            return TaskActionResponse(
                success=True,
                task_id=task_id,
                status="stopped",
                message="Stop signal sent to running task.",
            )

        job.cancel()
        with get_db_session() as session:
            TaskRepository(session).update_status(task_id, status="canceled", finished=True)
        return TaskActionResponse(
            success=True,
            task_id=task_id,
            status="canceled",
            message="Task canceled successfully.",
        )

    def retry_task(self, task_id: str) -> TaskActionResponse:
        job = self._safe_fetch_job(task_id)
        if job is None:
            return TaskActionResponse(
                success=False,
                task_id=task_id,
                status="unknown",
                message="Task not found.",
            )

        status = job.get_status(refresh=True)
        if status not in {"failed", "stopped", "canceled"}:
            return TaskActionResponse(
                success=False,
                task_id=task_id,
                status=status,
                message=f"Task cannot be retried from status '{status}'.",
            )

        payload = job.meta.get("payload")
        if not payload:
            return TaskActionResponse(
                success=False,
                task_id=task_id,
                status=status,
                message="Task payload is missing, cannot retry.",
            )

        retries_left = int(job.meta.get("retry_count", 0))
        if retries_left <= 0:
            return TaskActionResponse(
                success=False,
                task_id=task_id,
                status=status,
                message="No retries left for this task.",
            )

        new_task_id = str(uuid.uuid4())
        with get_db_session() as session:
            original_repo = TaskRepository(session)
            original_repo.update_status(task_id, status=status, retry_count=retries_left - 1)
            original_repo.create_task(
                task_id=new_task_id,
                queue_job_id=new_task_id,
                domain=payload["domain"],
                region=payload["region"],
                status="queued",
                request_payload=payload,
                retry_count=retries_left - 1,
            )
        new_job = self.queue_service.enqueue(
            "app.tasks.search_tasks.run_search_task",
            payload,
            job_id=new_task_id,
        )
        new_job.meta["retry_count"] = retries_left - 1
        new_job.save_meta()
        return TaskActionResponse(
            success=True,
            task_id=task_id,
            new_task_id=new_task_id,
            status="queued",
            message="Task retried successfully.",
        )

    def _safe_fetch_job(self, task_id: str):
        try:
            return self.queue_service.fetch_job(task_id)
        except (NoSuchJobError, InvalidJobOperation):
            return None
