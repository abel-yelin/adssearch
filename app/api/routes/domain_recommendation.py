from fastapi import APIRouter, Depends, HTTPException

from app.dependencies.services import get_domain_recommendation_service, get_whois_service
from app.schemas.domain_recommendation import (
    DomainRecommendationBlueprint,
    DomainRecommendationBlueprintRequest,
    DomainRecommendationCandidatesRequest,
    DomainRecommendationCandidatesResponse,
    DomainRecommendationWhoisRequest,
    DomainRecommendationWhoisResponse,
)
from app.services.domain_recommendation_service import DomainRecommendationService
from app.services.whois_service import WhoisService


router = APIRouter(prefix="/domain-recommendation", tags=["domain-recommendation"])


@router.post("/blueprint", response_model=DomainRecommendationBlueprint)
async def generate_domain_recommendation_blueprint(
    request: DomainRecommendationBlueprintRequest,
    service: DomainRecommendationService = Depends(get_domain_recommendation_service),
) -> DomainRecommendationBlueprint:
    return service.generate_blueprint(request.keyword)


@router.post("/candidates", response_model=DomainRecommendationCandidatesResponse)
async def generate_domain_recommendation_candidates(
    request: DomainRecommendationCandidatesRequest,
    service: DomainRecommendationService = Depends(get_domain_recommendation_service),
) -> DomainRecommendationCandidatesResponse:
    return service.build_candidate_board(request)


@router.post("/whois", response_model=DomainRecommendationWhoisResponse)
async def batch_check_domain_availability(
    request: DomainRecommendationWhoisRequest,
    service: WhoisService = Depends(get_whois_service),
) -> DomainRecommendationWhoisResponse:
    try:
        return DomainRecommendationWhoisResponse(results=service.check_domains(request.domains))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
