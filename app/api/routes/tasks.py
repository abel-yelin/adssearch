from fastapi import APIRouter, Depends

from app.dependencies.services import get_task_service
from app.schemas.search import SearchTaskStatusResponse
from app.services.task_service import TaskService


router = APIRouter(tags=["tasks"])


@router.get("/tasks/{task_id}", response_model=SearchTaskStatusResponse)
async def get_task(task_id: str, task_service: TaskService = Depends(get_task_service)) -> SearchTaskStatusResponse:
    return task_service.get_task_status(task_id)
