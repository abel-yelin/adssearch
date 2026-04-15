from fastapi import APIRouter, Depends, HTTPException

from app.collectors.sitedata_traffic_collector import SiteDataTrafficCollectorError
from app.dependencies.services import get_sitedata_service
from app.schemas.sitedata import SiteDataTrafficRequest, SiteDataTrafficResponse
from app.services.sitedata_service import SiteDataTrafficService


router = APIRouter(prefix="/sitedata", tags=["sitedata"])


@router.post("/traffic", response_model=SiteDataTrafficResponse)
async def fetch_sitedata_traffic(
    request: SiteDataTrafficRequest,
    service: SiteDataTrafficService = Depends(get_sitedata_service),
) -> SiteDataTrafficResponse:
    try:
        return await service.fetch_traffic(request)
    except SiteDataTrafficCollectorError as exc:
        status_code = 400 if exc.code == "invalid_domain" else 502
        raise HTTPException(status_code=status_code, detail={"code": exc.code, "message": exc.message}) from exc
