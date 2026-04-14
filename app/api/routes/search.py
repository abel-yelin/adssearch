from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies.services import get_ads_task_service
from app.schemas.search import SearchRequest, SearchTaskSubmitResponse
from app.services.ads_task_service import AdsTaskService


router = APIRouter(tags=["search"])


@router.post("/search", response_model=SearchTaskSubmitResponse, status_code=status.HTTP_202_ACCEPTED)
async def search_domain(
    request: SearchRequest,
    task_service: AdsTaskService = Depends(get_ads_task_service),
) -> SearchTaskSubmitResponse:
    try:
        return task_service.submit_search(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
