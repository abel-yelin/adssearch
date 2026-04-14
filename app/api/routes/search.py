import asyncio
import uuid

from fastapi import APIRouter

from app.schemas.search import SearchRequest, SearchResponse
from app.services.scraper import GoogleAdsTransparencyScraper


router = APIRouter(tags=["search"])


@router.post("/search", response_model=SearchResponse)
async def search_domain(request: SearchRequest) -> SearchResponse:
    task_id = str(uuid.uuid4())[:8]
    start_time = asyncio.get_event_loop().time()
    scraper = GoogleAdsTransparencyScraper(
        headless=True,
        proxy=request.proxy,
        region=request.region,
        max_scroll_pages=request.max_scroll_pages,
        timeout=request.timeout,
    )

    try:
        await scraper.start()
        result = await scraper.search_domain(request.domain)
        duration = asyncio.get_event_loop().time() - start_time
        return SearchResponse(
            success=True,
            task_id=task_id,
            data=result.to_dict(),
            duration_seconds=round(duration, 2),
        )
    except Exception as exc:
        duration = asyncio.get_event_loop().time() - start_time
        return SearchResponse(
            success=False,
            task_id=task_id,
            error=str(exc),
            duration_seconds=round(duration, 2),
        )
    finally:
        await scraper.close()
