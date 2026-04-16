import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.collectors.sitedata_traffic_collector import SiteDataTrafficCollectorError
from app.dependencies.services import get_pubspy_service, get_sitedata_service
from app.schemas.pubspy import (
    PubSpyAnalyzeRequest,
    PubSpyAnalyzeResponse,
    PubSpyKeywordSummary,
    PubSpyDomainMetricsRequest,
    PubSpyDomainMetricsResponse,
    PubSpyRelatedDomainsRequest,
    PubSpyRelatedDomainsResponse,
)
from app.schemas.sitedata import SiteDataTrafficRequest
from app.services.pubspy_service import PubSpyService
from app.services.sitedata_service import SiteDataTrafficService


router = APIRouter(prefix="/pubspy", tags=["pubspy"])


@router.post("/analyze", response_model=PubSpyAnalyzeResponse)
async def analyze_pubspy_target(
    request: PubSpyAnalyzeRequest,
    service: PubSpyService = Depends(get_pubspy_service),
    sitedata_service: SiteDataTrafficService = Depends(get_sitedata_service),
) -> PubSpyAnalyzeResponse:
    try:
        response = service.analyze(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if request.include_top_keywords:
        try:
            keywords_payload = await sitedata_service.fetch_traffic(
                SiteDataTrafficRequest(
                    domain=response.normalized_domain,
                    collection_mode=request.keyword_collection_mode,
                    proxy=request.keyword_proxy,
                    timeout_seconds=request.keyword_timeout_seconds,
                    browser_mode=request.keyword_browser_mode,
                    browser_cdp_url=request.keyword_browser_cdp_url,
                    browser_executable_path=request.keyword_browser_executable_path,
                    browser_user_data_dir=request.keyword_browser_user_data_dir,
                    browser_channel=request.keyword_browser_channel,
                    browser_extension_path=request.keyword_browser_extension_path,
                    browser_headless=request.keyword_browser_headless,
                    browser_timeout_ms=request.keyword_browser_timeout_ms,
                    browser_pre_click_wait_ms=request.keyword_browser_pre_click_wait_ms,
                    browser_post_click_wait_ms=request.keyword_browser_post_click_wait_ms,
                )
            )
            response.current_domain.top_keywords = [
                PubSpyKeywordSummary(
                    keyword=item.keyword,
                    volume=item.volume,
                    cpc=item.cpc,
                    estimated_value=item.estimated_value,
                )
                for item in keywords_payload.top_keywords
            ]
        except (SiteDataTrafficCollectorError, httpx.HTTPError, RuntimeError, ValueError) as exc:
            response.warnings.append(f"Top keyword enrichment failed: {exc}")

    return response


@router.post("/related-domains", response_model=PubSpyRelatedDomainsResponse)
async def get_pubspy_related_domains(
    request: PubSpyRelatedDomainsRequest,
    service: PubSpyService = Depends(get_pubspy_service),
) -> PubSpyRelatedDomainsResponse:
    try:
        return service.related_domains(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/domain-metrics", response_model=PubSpyDomainMetricsResponse)
async def get_pubspy_domain_metrics(
    request: PubSpyDomainMetricsRequest,
    service: PubSpyService = Depends(get_pubspy_service),
) -> PubSpyDomainMetricsResponse:
    try:
        return service.lookup_domain_metrics(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
