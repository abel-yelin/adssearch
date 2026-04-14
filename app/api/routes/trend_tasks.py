from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies.services import get_trend_task_service
from app.schemas.task import (
    TrendTaskActionResponse,
    TrendTaskCreateRequest,
    TrendTaskCreateResponse,
    TrendTaskExportResponse,
    TrendTaskStatusResponse,
    TrendTaskSummaryResponse,
)
from app.services.task_service import TaskService


router = APIRouter(prefix="/trends", tags=["trends"])


@router.post("/tasks", response_model=TrendTaskCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_trend_task(
    request: TrendTaskCreateRequest,
    task_service: TaskService = Depends(get_trend_task_service),
) -> TrendTaskCreateResponse:
    try:
        return task_service.create_task(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/tasks/{task_id}", response_model=TrendTaskStatusResponse)
async def get_trend_task(
    task_id: str,
    task_service: TaskService = Depends(get_trend_task_service),
) -> TrendTaskStatusResponse:
    try:
        return task_service.get_task_status(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/tasks/{task_id}/summary", response_model=TrendTaskSummaryResponse)
async def get_trend_task_summary(
    task_id: str,
    task_service: TaskService = Depends(get_trend_task_service),
) -> TrendTaskSummaryResponse:
    try:
        return task_service.get_task_summary(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/tasks/{task_id}/export", response_model=TrendTaskExportResponse)
async def export_trend_task(
    task_id: str,
    task_service: TaskService = Depends(get_trend_task_service),
) -> TrendTaskExportResponse:
    try:
        return task_service.export_task(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/tasks/{task_id}/cancel", response_model=TrendTaskActionResponse)
async def cancel_trend_task(
    task_id: str,
    task_service: TaskService = Depends(get_trend_task_service),
) -> TrendTaskActionResponse:
    try:
        return task_service.cancel_task(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/tasks/{task_id}/retry", response_model=TrendTaskActionResponse)
async def retry_trend_task(
    task_id: str,
    task_service: TaskService = Depends(get_trend_task_service),
) -> TrendTaskActionResponse:
    try:
        return task_service.retry_task(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
