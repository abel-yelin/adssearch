from fastapi import APIRouter, Depends

from app.dependencies.services import get_task_service
from app.schemas.search import SearchTaskStatusResponse, TaskActionResponse
from app.services.task_service import TaskService


router = APIRouter(tags=["tasks"])


@router.get("/tasks/{task_id}", response_model=SearchTaskStatusResponse)
async def get_task(task_id: str, task_service: TaskService = Depends(get_task_service)) -> SearchTaskStatusResponse:
    return task_service.get_task_status(task_id)


@router.post("/tasks/{task_id}/cancel", response_model=TaskActionResponse)
async def cancel_task(task_id: str, task_service: TaskService = Depends(get_task_service)) -> TaskActionResponse:
    return task_service.cancel_task(task_id)


@router.post("/tasks/{task_id}/retry", response_model=TaskActionResponse)
async def retry_task(task_id: str, task_service: TaskService = Depends(get_task_service)) -> TaskActionResponse:
    return task_service.retry_task(task_id)
