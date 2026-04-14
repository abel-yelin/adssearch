from app.core.config import get_settings
from app.services.ads_task_service import AdsTaskService
from app.services.queue_service import TaskQueueService
from app.services.search_service import SearchService
from app.services.sitemap_service import SitemapService
from app.services.task_service import TaskService


def get_search_service() -> SearchService:
    return SearchService()


def get_queue_service() -> TaskQueueService:
    return TaskQueueService(get_settings())


def get_ads_task_service() -> AdsTaskService:
    return AdsTaskService(get_queue_service())


def get_trend_task_service() -> TaskService:
    return TaskService(get_queue_service())


def get_sitemap_service() -> SitemapService:
    settings = get_settings()
    return SitemapService(TaskQueueService(settings), settings)
