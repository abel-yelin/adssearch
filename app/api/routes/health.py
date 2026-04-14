from datetime import UTC, datetime

from fastapi import APIRouter, Depends

from app.core.config import AppSettings, get_settings
from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(settings: AppSettings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        timestamp=datetime.now(UTC).isoformat(),
        environment=settings.app_env,
        version=settings.version,
    )
