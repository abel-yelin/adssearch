from fastapi import APIRouter

from app.api.routes.domain_recommendation import router as domain_recommendation_router
from app.api.routes.health import router as health_router
from app.api.routes.free_trends import router as free_trends_router
from app.api.routes.search import router as search_router
from app.api.routes.sitedata import router as sitedata_router
from app.api.routes.sitemaps import router as sitemaps_router
from app.api.routes.tasks import router as tasks_router
from app.api.routes.trend_discovery import router as trend_discovery_router
from app.api.routes.trend_tasks import router as trend_tasks_router


api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(domain_recommendation_router)
api_router.include_router(free_trends_router)
api_router.include_router(search_router)
api_router.include_router(sitedata_router)
api_router.include_router(sitemaps_router)
api_router.include_router(tasks_router)
api_router.include_router(trend_tasks_router)
api_router.include_router(trend_discovery_router)
