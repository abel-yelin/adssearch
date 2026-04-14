import asyncio
import uuid

from app.core.config import AppSettings
from app.core.logging import get_logger
from app.schemas.search import SearchRequest
from app.services.scraper import GoogleAdsTransparencyScraper


logger = get_logger(__name__)


class SearchService:
    async def run_search(self, request: SearchRequest, settings: AppSettings, task_id: str | None = None) -> dict:
        task_id = task_id or str(uuid.uuid4())[:8]
        start_time = asyncio.get_event_loop().time()
        scraper = GoogleAdsTransparencyScraper(
            headless=True,
            proxy=request.proxy,
            region=request.region or settings.default_region,
            max_scroll_pages=request.max_scroll_pages or settings.default_max_scroll_pages,
            timeout=request.timeout or settings.default_timeout_ms,
        )

        try:
            await scraper.start()
            result = await scraper.search_domain(request.domain)
            duration = asyncio.get_event_loop().time() - start_time
            logger.info(
                "Domain search completed: domain=%s has_ads=%s ads=%s",
                request.domain,
                result.has_ads,
                result.total_ads_found,
            )
            return {
                "success": True,
                "task_id": task_id,
                "data": result.to_dict(),
                "duration_seconds": round(duration, 2),
            }
        except Exception as exc:
            duration = asyncio.get_event_loop().time() - start_time
            logger.exception("Domain search failed: domain=%s", request.domain)
            return {
                "success": False,
                "task_id": task_id,
                "error": str(exc),
                "duration_seconds": round(duration, 2),
            }
        finally:
            await scraper.close()
