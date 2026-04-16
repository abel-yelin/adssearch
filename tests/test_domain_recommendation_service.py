from app.schemas.domain_recommendation import (
    DomainRecommendationCandidatesRequest,
    FeaturedDomainSuggestion,
    RecommendationRoot,
)
from app.services.domain_recommendation_service import (
    DomainRecommendationService,
    build_letter_candidates,
    calculate_domain_score,
    merge_roots,
    parse_blueprint_payload,
)


def test_merge_roots_keeps_seed_first_and_dedupes():
    roots = merge_roots(
        "travel",
        [
            RecommendationRoot(
                word="travel",
                label="travel",
                category="Seed keyword",
                relevance=1.0,
                kind="semantic",
            ),
            RecommendationRoot(
                word="voyage",
                label="voyage",
                category="Related concept",
                relevance=0.84,
                kind="semantic",
            ),
        ],
        [
            RecommendationRoot(
                word="viaje",
                label="viaje · Spanish",
                category="Translation",
                relevance=0.8,
                kind="multilingual",
                language="Spanish",
            )
        ],
    )

    assert [item.word for item in roots] == ["travel", "voyage", "viaje"]
    assert roots[2].label == "viaje · Spanish"


def test_letter_candidates_produce_expected_counts():
    result = build_letter_candidates("travel", "travel", "com")
    assert len(result.single_prefix) == 26
    assert len(result.single_suffix) == 26
    assert len(result.double_prefix) == 676
    assert len(result.double_suffix) == 676
    assert result.double_prefix[0].score.total >= result.double_prefix[-1].score.total


def test_calculate_domain_score_penalizes_protected_brand_tokens():
    safe = calculate_domain_score("travelnest", "travel")
    risky = calculate_domain_score("openaiforge", "travel")
    assert safe.brand_safety > risky.brand_safety
    assert safe.total > risky.total


def test_parse_blueprint_payload_extracts_fenced_json():
    payload = parse_blueprint_payload(
        """
        Here is the blueprint:
        ```json
        {"positioning":"Short line","insights":["a"],"semanticRoots":[],"multilingualRoots":[],"suggestedPrefixes":["go"],"suggestedSuffixes":["lab"]}
        ```
        """
    )
    assert payload["positioning"] == "Short line"
    assert payload["suggestedPrefixes"] == ["go"]


def test_build_candidate_board_returns_expected_shape():
    service = DomainRecommendationService()
    response = service.build_candidate_board(
        DomainRecommendationCandidatesRequest(
            keyword="travel",
            root="voyage",
            suggested_prefixes=["go", "smart"],
            suggested_suffixes=["lab", "hub"],
            featured_suggestions=[
                FeaturedDomainSuggestion(
                    name="voyago",
                    tld="com",
                    full_domain="voyago.com",
                    type="brandable",
                    reason="Compact and memorable.",
                ),
                FeaturedDomainSuggestion(
                    name="tripzen",
                    tld="com",
                    full_domain="tripzen.com",
                    type="brandable",
                    reason="Travel-focused and calm.",
                ),
            ],
        )
    )

    assert response.keyword == "travel"
    assert response.root == "voyage"
    assert len(response.overview) == 10
    assert len(response.featured) == 2
    assert len(response.digits.prefix) == 10
    assert len(response.letters.double_suffix) == 676
    assert len(response.affixes.prefix) == 2
    assert len(response.affixes.suffix) == 2
    assert response.total_candidates == 1430
