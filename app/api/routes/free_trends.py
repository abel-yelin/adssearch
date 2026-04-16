from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies.services import get_free_trends_service
from app.schemas.free_trends import (
    FreeTrendsRunResultsResponse,
    FreeTrendsRunSummaryResponse,
    FreeTrendsSeedCreateRequest,
    FreeTrendsSeedDeleteResponse,
    FreeTrendsSeedItem,
    FreeTrendsSeedsListResponse,
    FreeTrendsSeedsBulkReplaceRequest,
    FreeTrendsSeedsReplaceRequest,
    FreeTrendsSeedsResponse,
    FreeTrendsSeedUpdateRequest,
    FreeTrendsStatusResponse,
)
from app.schemas.free_trends_requests import FreeTrendsRunRequestResponse
from app.services.free_trends_service import FreeTrendsApiService


router = APIRouter(prefix="/free-trends", tags=["free-trends"])


@router.get("/status", response_model=FreeTrendsStatusResponse)
async def get_free_trends_status(service: FreeTrendsApiService = Depends(get_free_trends_service)) -> FreeTrendsStatusResponse:
    return service.get_status()


@router.get("/seeds", response_model=FreeTrendsSeedsListResponse)
async def list_free_trends_seeds(
    service: FreeTrendsApiService = Depends(get_free_trends_service),
    search: str | None = Query(default=None),
    group_key: str | None = Query(default=None),
    enabled: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    sort_by: Literal["priority", "term", "updated_at", "created_at", "last_scanned_at"] = Query(default="priority"),
    sort_order: Literal["asc", "desc"] = Query(default="desc"),
) -> FreeTrendsSeedsListResponse:
    return service.list_seeds(
        search=search,
        group_key=group_key,
        enabled=enabled,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.put("/seeds", response_model=FreeTrendsSeedsResponse)
async def replace_free_trends_seeds(
    request: FreeTrendsSeedsReplaceRequest,
    service: FreeTrendsApiService = Depends(get_free_trends_service),
) -> FreeTrendsSeedsResponse:
    return service.replace_seeds(request.root_terms)


@router.post("/seeds", response_model=FreeTrendsSeedItem, status_code=status.HTTP_201_CREATED)
async def create_free_trends_seed(
    request: FreeTrendsSeedCreateRequest,
    service: FreeTrendsApiService = Depends(get_free_trends_service),
) -> FreeTrendsSeedItem:
    try:
        return service.create_seed(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/seeds/{seed_id}", response_model=FreeTrendsSeedItem)
async def update_free_trends_seed(
    seed_id: int,
    request: FreeTrendsSeedUpdateRequest,
    service: FreeTrendsApiService = Depends(get_free_trends_service),
) -> FreeTrendsSeedItem:
    try:
        return service.update_seed(seed_id, request)
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.delete("/seeds/{seed_id}", response_model=FreeTrendsSeedDeleteResponse)
async def delete_free_trends_seed(
    seed_id: int,
    service: FreeTrendsApiService = Depends(get_free_trends_service),
) -> FreeTrendsSeedDeleteResponse:
    try:
        return service.delete_seed(seed_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/seeds/bulk-replace", response_model=FreeTrendsSeedsResponse)
async def bulk_replace_free_trends_seeds(
    request: FreeTrendsSeedsBulkReplaceRequest,
    service: FreeTrendsApiService = Depends(get_free_trends_service),
) -> FreeTrendsSeedsResponse:
    return service.bulk_replace_seed_items(request.items)


@router.get("/runs/latest", response_model=FreeTrendsRunSummaryResponse)
async def get_latest_free_trends_run(
    service: FreeTrendsApiService = Depends(get_free_trends_service),
) -> FreeTrendsRunSummaryResponse:
    try:
        return service.get_latest_run()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs/{run_id}", response_model=FreeTrendsRunSummaryResponse)
async def get_free_trends_run(
    run_id: str,
    service: FreeTrendsApiService = Depends(get_free_trends_service),
) -> FreeTrendsRunSummaryResponse:
    try:
        return service.get_run(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs/{run_id}/results", response_model=FreeTrendsRunResultsResponse)
async def get_free_trends_run_results(
    run_id: str,
    service: FreeTrendsApiService = Depends(get_free_trends_service),
) -> FreeTrendsRunResultsResponse:
    try:
        return service.get_run_results(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runs", response_model=FreeTrendsRunRequestResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_free_trends_run(
    service: FreeTrendsApiService = Depends(get_free_trends_service),
) -> FreeTrendsRunRequestResponse:
    return service.create_run_request()


@router.get("/run-requests/{request_id}", response_model=FreeTrendsRunRequestResponse)
async def get_free_trends_run_request(
    request_id: str,
    service: FreeTrendsApiService = Depends(get_free_trends_service),
) -> FreeTrendsRunRequestResponse:
    try:
        return service.get_run_request(request_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
