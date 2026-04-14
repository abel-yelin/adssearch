from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.services.queue_service import TaskQueueService
from app.services.sitemap_service import SitemapService


logger = get_logger(__name__)


def run_sitemap_monitor_task(payload: dict) -> dict:
    settings = get_settings()
    configure_logging(settings.log_level)
    monitor_id = payload["monitor_id"]
    run_id = payload["run_id"]
    service = SitemapService(TaskQueueService(settings), settings)
    try:
        logger.info("Worker executing sitemap monitor: monitor_id=%s run_id=%s", monitor_id, run_id)
        return service.execute_run(monitor_id, run_id)
    except Exception as exc:
        logger.exception("Sitemap monitor failed: monitor_id=%s run_id=%s", monitor_id, run_id)
        service.fail_run(monitor_id, run_id, str(exc))
        raise
