import time
import uuid
from datetime import UTC, datetime

from app import models  # noqa: F401
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.session import get_db_session
from app.repositories.sitemap_repository import SitemapRepository
from app.services.queue_service import TaskQueueService


logger = get_logger(__name__)


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    queue_service = TaskQueueService(settings)
    logger.info("Starting sitemap scheduler with poll=%ss", settings.sitemap_scheduler_poll_seconds)

    while True:
        _dispatch_due_monitors(queue_service, settings.sitemap_scheduler_batch_size)
        time.sleep(settings.sitemap_scheduler_poll_seconds)


def _dispatch_due_monitors(queue_service: TaskQueueService, batch_size: int) -> None:
    now = datetime.now(UTC)
    pending_jobs: list[tuple[str, str]] = []
    with get_db_session() as session:
        repo = SitemapRepository(session)
        due_monitors = repo.list_due_monitors(now, batch_size)
        for monitor in due_monitors:
            if repo.has_active_run(monitor.id):
                continue
            run_id = str(uuid.uuid4())
            repo.create_run(run_id=run_id, monitor_id=monitor.id, trigger_mode="scheduled")
            pending_jobs.append((monitor.id, run_id))

    for monitor_id, run_id in pending_jobs:
        queue_service.enqueue(
            "app.tasks.sitemap_tasks.run_sitemap_monitor_task",
            {"monitor_id": monitor_id, "run_id": run_id},
            job_id=run_id,
        )
        logger.info("Scheduled sitemap monitor run: monitor_id=%s run_id=%s", monitor_id, run_id)


if __name__ == "__main__":
    main()
