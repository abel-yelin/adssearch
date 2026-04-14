from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies.services import get_sitemap_service
from app.schemas.sitemap import (
    SitemapMonitorCreateRequest,
    SitemapMonitorCreateResponse,
    SitemapMonitorListResponse,
    SitemapMonitorResponse,
    SitemapRecentUrlsResponse,
    SitemapRunDispatchResponse,
    SitemapRunResponse,
)
from app.services.sitemap_service import SitemapService


router = APIRouter(prefix="/sitemaps", tags=["sitemaps"])


@router.post("/monitors", response_model=SitemapMonitorCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_sitemap_monitor(
    request: SitemapMonitorCreateRequest,
    service: SitemapService = Depends(get_sitemap_service),
) -> SitemapMonitorCreateResponse:
    try:
        return service.create_monitor(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/monitors", response_model=SitemapMonitorListResponse)
async def list_sitemap_monitors(service: SitemapService = Depends(get_sitemap_service)) -> SitemapMonitorListResponse:
    return service.list_monitors()


@router.get("/monitors/{monitor_id}", response_model=SitemapMonitorResponse)
async def get_sitemap_monitor(
    monitor_id: str,
    service: SitemapService = Depends(get_sitemap_service),
) -> SitemapMonitorResponse:
    try:
        return service.get_monitor(monitor_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/monitors/{monitor_id}/run", response_model=SitemapRunDispatchResponse, status_code=status.HTTP_202_ACCEPTED)
async def run_sitemap_monitor(
    monitor_id: str,
    service: SitemapService = Depends(get_sitemap_service),
) -> SitemapRunDispatchResponse:
    try:
        return service.dispatch_run(monitor_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/runs/{run_id}", response_model=SitemapRunResponse)
async def get_sitemap_run(
    run_id: str,
    service: SitemapService = Depends(get_sitemap_service),
) -> SitemapRunResponse:
    try:
        return service.get_run(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/monitors/{monitor_id}/recent-new-urls", response_model=SitemapRecentUrlsResponse)
async def get_recent_new_urls(
    monitor_id: str,
    service: SitemapService = Depends(get_sitemap_service),
) -> SitemapRecentUrlsResponse:
    try:
        return service.get_recent_new_urls(monitor_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
