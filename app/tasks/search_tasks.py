import asyncio

from rq import get_current_job

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.session import get_db_session
from app.models.statuses import SearchTaskStatus
from app.schemas.search import SearchRequest
from app.repositories.task_repository import TaskRepository
from app.services.search_service import SearchService


logger = get_logger(__name__)


def run_search_task(payload: dict) -> dict:
    settings = get_settings()
    configure_logging(settings.log_level)
    request = SearchRequest(**payload)
    job = get_current_job()
    task_id = job.id if job else None
    logger.info("Worker executing search task for domain=%s", request.domain)
    if task_id:
        with get_db_session() as session:
            TaskRepository(session).update_status(task_id, status=SearchTaskStatus.RUNNING.value, started=True)

    result = asyncio.run(SearchService().run_search(request, settings, task_id=task_id))

    if task_id:
        with get_db_session() as session:
            repo = TaskRepository(session)
            if result.get("success"):
                repo.update_status(
                    task_id,
                    status=SearchTaskStatus.COMPLETED.value,
                    result_payload=result,
                    error_message=None,
                    finished=True,
                )
            else:
                repo.update_status(
                    task_id,
                    status=SearchTaskStatus.FAILED.value,
                    result_payload=result,
                    error_message=result.get("error"),
                    finished=True,
                )
    return result
