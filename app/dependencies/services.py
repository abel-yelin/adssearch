from app.core.config import get_settings
from app.services.queue_service import TaskQueueService
from app.services.search_service import SearchService
from app.services.task_service import TaskService


def get_search_service() -> SearchService:
    return SearchService()


def get_queue_service() -> TaskQueueService:
    return TaskQueueService(get_settings())


def get_task_service() -> TaskService:
    return TaskService(get_queue_service())
