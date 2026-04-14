from datetime import datetime

from fastapi import APIRouter


router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}
