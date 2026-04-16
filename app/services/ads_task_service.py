import uuid

from rq.exceptions import InvalidJobOperation, NoSuchJobError

from app.db.session import get_db_session
from app.models.statuses import SearchTaskLookupStatus, SearchTaskStatus
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
                status=SearchTaskStatus.PENDING.value,
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
            status=SearchTaskStatus.PENDING,
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
                status=SearchTaskLookupStatus.UNKNOWN,
                error="Task not found.",
            )

        status = SearchTaskLookupStatus(task.status)
        retries_left = task.retry_count
        result = task.result_payload
        error = task.error_message
        return SearchTaskStatusResponse(
            success=status != SearchTaskLookupStatus.FAILED,
            task_id=task_id,
            status=status,
            result=result,
            error=error,
            retries_left=retries_left,
        )

    def cancel_task(self, task_id: str) -> TaskActionResponse:
        with get_db_session() as session:
            repo = TaskRepository(session)
            task = repo.get_by_task_id(task_id)
            if task is None:
                return TaskActionResponse(
                    success=False,
                    task_id=task_id,
                    status=SearchTaskLookupStatus.UNKNOWN,
                    message="Task not found.",
                )
            status = SearchTaskLookupStatus(task.status)
            if status in {
                SearchTaskLookupStatus.COMPLETED,
                SearchTaskLookupStatus.FAILED,
                SearchTaskLookupStatus.CANCELLED,
            }:
                return TaskActionResponse(
                    success=False,
                    task_id=task_id,
                    status=status,
                    message=f"Task cannot be canceled from status '{status}'.",
                )
            repo.update_status(task_id, status=SearchTaskStatus.CANCELLED.value, finished=True)

        job = self._safe_fetch_job(task_id)
        if job is None:
            return TaskActionResponse(
                success=True,
                task_id=task_id,
                status=SearchTaskLookupStatus.CANCELLED,
                message="Task canceled in database; no active queue job was found.",
            )

        queue_status = self._map_queue_status(job.get_status(refresh=True))
        if status == SearchTaskLookupStatus.RUNNING:
            if queue_status == SearchTaskLookupStatus.RUNNING:
                self.queue_service.stop_job(task_id)
            return TaskActionResponse(
                success=True,
                task_id=task_id,
                status=SearchTaskLookupStatus.CANCELLED,
                message="Cancel signal sent to running task.",
            )

        if queue_status == SearchTaskLookupStatus.PENDING:
            job.cancel()
        return TaskActionResponse(
            success=True,
            task_id=task_id,
            status=SearchTaskLookupStatus.CANCELLED,
            message="Task canceled successfully.",
        )

    def retry_task(self, task_id: str) -> TaskActionResponse:
        with get_db_session() as session:
            repo = TaskRepository(session)
            task = repo.get_by_task_id(task_id)
            if task is None:
                return TaskActionResponse(
                    success=False,
                    task_id=task_id,
                    status=SearchTaskLookupStatus.UNKNOWN,
                    message="Task not found.",
                )

            status = SearchTaskLookupStatus(task.status)
            if status not in {SearchTaskLookupStatus.FAILED, SearchTaskLookupStatus.CANCELLED}:
                return TaskActionResponse(
                    success=False,
                    task_id=task_id,
                    status=status,
                    message=f"Task cannot be retried from status '{status}'.",
                )

            payload = task.request_payload
            retries_left = int(task.retry_count or 0)
            if not payload:
                return TaskActionResponse(
                    success=False,
                    task_id=task_id,
                    status=status,
                    message="Task payload is missing, cannot retry.",
                )
            if retries_left <= 0:
                return TaskActionResponse(
                    success=False,
                    task_id=task_id,
                    status=status,
                    message="No retries left for this task.",
                )

            new_task_id = str(uuid.uuid4())
            repo.update_status(task_id, status=status.value, retry_count=retries_left - 1)
            repo.create_task(
                task_id=new_task_id,
                queue_job_id=new_task_id,
                domain=payload["domain"],
                region=payload["region"],
                status=SearchTaskStatus.PENDING.value,
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
            status=SearchTaskLookupStatus.PENDING,
            message="Task retried successfully.",
        )

    def _safe_fetch_job(self, task_id: str):
        try:
            return self.queue_service.fetch_job(task_id)
        except (NoSuchJobError, InvalidJobOperation):
            return None

    def _map_queue_status(self, status: str) -> SearchTaskLookupStatus:
        mapping = {
            "queued": SearchTaskLookupStatus.PENDING,
            "scheduled": SearchTaskLookupStatus.PENDING,
            "deferred": SearchTaskLookupStatus.PENDING,
            "started": SearchTaskLookupStatus.RUNNING,
            "finished": SearchTaskLookupStatus.COMPLETED,
            "failed": SearchTaskLookupStatus.FAILED,
            "stopped": SearchTaskLookupStatus.CANCELLED,
            "canceled": SearchTaskLookupStatus.CANCELLED,
            "cancelled": SearchTaskLookupStatus.CANCELLED,
        }
        return mapping.get(status, SearchTaskLookupStatus.UNKNOWN)
