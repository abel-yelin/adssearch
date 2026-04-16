from app.core.config import get_settings
from app.services.ads_task_service import AdsTaskService
from app.services.domain_recommendation_service import DomainRecommendationService
from app.services.free_trends_service import FreeTrendsApiService
from app.services.pubspy_service import PubSpyService
from app.services.queue_service import TaskQueueService
from app.services.search_service import SearchService
from app.services.sitedata_service import SiteDataTrafficService
from app.services.sitemap_service import SitemapService
from app.services.task_service import TaskService
from app.services.trend_discovery_service import TrendDiscoveryService
from app.services.whois_service import WhoisService


def get_search_service() -> SearchService:
    return SearchService()


def get_queue_service() -> TaskQueueService:
    return TaskQueueService(get_settings())


def get_ads_task_service() -> AdsTaskService:
    return AdsTaskService(get_queue_service())


def get_trend_task_service() -> TaskService:
    return TaskService(get_queue_service())


def get_trend_discovery_service() -> TrendDiscoveryService:
    return TrendDiscoveryService()


def get_sitemap_service() -> SitemapService:
    settings = get_settings()
    return SitemapService(TaskQueueService(settings), settings)


def get_sitedata_service() -> SiteDataTrafficService:
    return SiteDataTrafficService()


def get_free_trends_service() -> FreeTrendsApiService:
    return FreeTrendsApiService(get_settings())


def get_domain_recommendation_service() -> DomainRecommendationService:
    return DomainRecommendationService(get_settings())


def get_whois_service() -> WhoisService:
    return WhoisService(get_settings())


def get_pubspy_service() -> PubSpyService:
    settings = get_settings()
    return PubSpyService(settings=settings, whois_service=WhoisService(settings))
