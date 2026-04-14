import uuid

from rq.exceptions import NoSuchJobError

from app.core.config import AppSettings
from app.schemas.search import SearchRequest, SearchTaskStatusResponse, SearchTaskSubmitResponse
from app.services.queue_service import TaskQueueService


class TaskService:
    def __init__(self, queue_service: TaskQueueService):
        self.queue_service = queue_service

    def submit_search(self, request: SearchRequest) -> SearchTaskSubmitResponse:
        task_id = str(uuid.uuid4())
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
        try:
            job = self.queue_service.fetch_job(task_id)
        except NoSuchJobError:
            job = None

        if job is None:
            return SearchTaskStatusResponse(
                success=False,
                task_id=task_id,
                status="unknown",
                error="Task not found.",
            )

        status = job.get_status(refresh=True)
        result = job.result if status == "finished" else None
        error = job.exc_info if status == "failed" else None
        return SearchTaskStatusResponse(
            success=status != "failed",
            task_id=task_id,
            status=status,
            result=result,
            error=error,
        )
