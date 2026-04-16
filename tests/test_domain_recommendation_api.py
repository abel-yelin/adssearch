from app.dependencies.services import get_domain_recommendation_service, get_whois_service
from app.schemas.domain_recommendation import (
    DomainAvailabilityResult,
    DomainCandidate,
    DomainRecommendationBlueprint,
    DomainRecommendationCandidatesResponse,
    DomainScoreBreakdown,
    FeaturedDomainSuggestion,
    RecommendationRoot,
)


def build_candidate(name: str) -> DomainCandidate:
    return DomainCandidate(
        method="featured",
        group="AI highlighted",
        name=name,
        tld="com",
        full_domain=f"{name}.com",
        reason="Short and clear.",
        score=DomainScoreBreakdown(
            memorability=8.8,
            pronunciation=8.5,
            brand_safety=9.1,
            seo=8.0,
            investment=8.3,
            total=8.6,
        ),
    )


class FakeDomainRecommendationService:
    def generate_blueprint(self, keyword: str) -> DomainRecommendationBlueprint:
        return DomainRecommendationBlueprint(
            keyword=keyword,
            provider="heuristic",
            fallback_used=False,
            positioning="A concise naming board.",
            insights=["Keep it short.", "Prioritize .com.", "Use semantic roots first."],
            semantic_roots=[
                RecommendationRoot(
                    word="voyage",
                    label="voyage",
                    category="Adjacent concept",
                    relevance=0.91,
                    kind="semantic",
                )
            ],
            multilingual_roots=[
                RecommendationRoot(
                    word="viaje",
                    label="viaje · Spanish",
                    category="Translation",
                    relevance=0.81,
                    kind="multilingual",
                    language="Spanish",
                )
            ],
            suggested_prefixes=["go", "smart"],
            suggested_suffixes=["lab", "hub"],
            featured_suggestions=[
                FeaturedDomainSuggestion(
                    name="voyagely",
                    tld="com",
                    full_domain="voyagely.com",
                    type="brandable",
                    reason="Compact and polished.",
                )
            ],
        )

    def build_candidate_board(self, request) -> DomainRecommendationCandidatesResponse:
        candidate = build_candidate("voyagely")
        return DomainRecommendationCandidatesResponse(
            keyword=request.keyword,
            root=request.root,
            tld=request.tld,
            overview=[candidate],
            featured=[candidate],
            digits={"prefix": [], "suffix": []},
            letters={
                "single_prefix": [],
                "single_suffix": [],
                "double_prefix": [],
                "double_suffix": [],
            },
            affixes={"prefix": [], "suffix": []},
            total_candidates=1,
        )


class FakeWhoisService:
    def check_domains(self, domains: list[str]) -> list[DomainAvailabilityResult]:
        return [
            DomainAvailabilityResult(
                domain=domain,
                available=(domain == "voyagely.com"),
                error=False,
            )
            for domain in domains
        ]


def test_domain_recommendation_blueprint_endpoint(client):
    from app.main import app

    app.dependency_overrides[get_domain_recommendation_service] = lambda: FakeDomainRecommendationService()
    try:
        response = client.post("/api/domain-recommendation/blueprint", json={"keyword": "travel"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["keyword"] == "travel"
    assert payload["provider"] == "heuristic"
    assert payload["semantic_roots"][0]["word"] == "voyage"


def test_domain_recommendation_candidates_endpoint(client):
    from app.main import app

    app.dependency_overrides[get_domain_recommendation_service] = lambda: FakeDomainRecommendationService()
    try:
        response = client.post(
            "/api/domain-recommendation/candidates",
            json={
                "keyword": "travel",
                "root": "voyage",
                "featured_suggestions": [],
                "suggested_prefixes": ["go"],
                "suggested_suffixes": ["lab"],
                "tld": "com",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["root"] == "voyage"
    assert payload["overview"][0]["name"] == "voyagely"
    assert payload["total_candidates"] == 1


def test_domain_recommendation_whois_endpoint(client):
    from app.main import app

    app.dependency_overrides[get_whois_service] = lambda: FakeWhoisService()
    try:
        response = client.post(
            "/api/domain-recommendation/whois",
            json={"domains": ["voyagely.com", "atlasforge.com"]},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["results"][0]["domain"] == "voyagely.com"
    assert payload["results"][0]["available"] is True
    assert payload["results"][1]["available"] is False
