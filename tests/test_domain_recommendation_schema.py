import pytest
from pydantic import ValidationError

from app.schemas.domain_recommendation import (
    DomainRecommendationBlueprintRequest,
    DomainRecommendationCandidatesRequest,
    DomainRecommendationWhoisRequest,
    FeaturedDomainSuggestion,
)


def test_blueprint_request_normalizes_keyword():
    request = DomainRecommendationBlueprintRequest(keyword="  Travel AI  ")
    assert request.keyword == "travel ai"


def test_candidates_request_normalizes_core_fields():
    request = DomainRecommendationCandidatesRequest(
        keyword=" Travel ",
        root=" Voyage ",
        tld=".COM",
        featured_suggestions=[
            FeaturedDomainSuggestion(
                name="voyago",
                tld="com",
                full_domain="voyago.com",
                type="brandable",
                reason="Short and brandable.",
            )
        ],
        suggested_prefixes=[" Go ", "Smart"],
        suggested_suffixes=["Lab", " Hub "],
    )

    assert request.keyword == "travel"
    assert request.root == "voyage"
    assert request.tld == "com"
    assert request.suggested_prefixes == ["go", "smart"]
    assert request.suggested_suffixes == ["lab", "hub"]


def test_candidates_request_rejects_invalid_root():
    with pytest.raises(ValidationError):
        DomainRecommendationCandidatesRequest(keyword="travel", root="vo!yage")


def test_whois_request_dedupes_and_normalizes_domains():
    request = DomainRecommendationWhoisRequest(domains=[" Example.com ", "example.com", "travel.ai"])
    assert request.domains == ["example.com", "travel.ai"]


def test_whois_request_rejects_invalid_domain():
    with pytest.raises(ValidationError):
        DomainRecommendationWhoisRequest(domains=["not a domain"])
