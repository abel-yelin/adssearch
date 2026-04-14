from fastapi import APIRouter, Depends, status

from app.dependencies.services import get_task_service
from app.schemas.search import SearchRequest, SearchTaskSubmitResponse
from app.services.task_service import TaskService


router = APIRouter(tags=["search"])


@router.post("/search", response_model=SearchTaskSubmitResponse, status_code=status.HTTP_202_ACCEPTED)
async def search_domain(
    request: SearchRequest,
    task_service: TaskService = Depends(get_task_service),
) -> SearchTaskSubmitResponse:
    return task_service.submit_search(request)
