import asyncio

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.schemas.search import SearchRequest
from app.services.search_service import SearchService


logger = get_logger(__name__)


def run_search_task(payload: dict) -> dict:
    settings = get_settings()
    configure_logging(settings.log_level)
    request = SearchRequest(**payload)
    logger.info("Worker executing search task for domain=%s", request.domain)
    response = asyncio.run(SearchService().run_search(request, settings))
    return response.model_dump()
