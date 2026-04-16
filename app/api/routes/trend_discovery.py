from fastapi import APIRouter, Depends, HTTPException

from app.dependencies.services import get_trend_discovery_service
from app.schemas.trend_discovery import TrendDiscoveryRequest, TrendDiscoveryResponse
from app.services.trend_discovery_service import TrendDiscoveryService, TrendProviderError


router = APIRouter(prefix="/trends/root-discovery", tags=["trends"])


@router.post("", response_model=TrendDiscoveryResponse)
async def discover_trend_risers(
    request: TrendDiscoveryRequest,
    service: TrendDiscoveryService = Depends(get_trend_discovery_service),
) -> TrendDiscoveryResponse:
    try:
        return service.discover(request)
    except TrendProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
