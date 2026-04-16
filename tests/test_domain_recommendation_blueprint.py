from app.services.domain_recommendation_service import (
    DomainRecommendationProviderError,
    DomainRecommendationService,
    HeuristicBlueprintProvider,
)


class FakeBlueprintProvider:
    provider_name = "reelxai"

    def generate(self, keyword: str) -> dict:
        assert keyword == "travel"
        return {
            "positioning": "A premium travel naming board.",
            "insights": ["Keep it short.", "Lean into movement.", "Prioritize .com."],
            "semanticRoots": [
                {"word": "voyage", "category": "Adjacent concept", "relevance": 0.92},
                {"word": "atlas", "category": "Metaphor", "relevance": 0.84},
            ],
            "multilingualRoots": [
                {
                    "word": "viaje",
                    "language": "Spanish",
                    "category": "Translation",
                    "relevance": 0.81,
                }
            ],
            "suggestedPrefixes": ["go", "smart", "nova"],
            "suggestedSuffixes": ["lab", "hub", "forge"],
            "featuredSuggestions": [
                {
                    "name": "voyagely",
                    "tld": "com",
                    "fullDomain": "voyagely.com",
                    "type": "brandable",
                    "reason": "Compact and polished.",
                }
            ],
        }


class FailingBlueprintProvider:
    provider_name = "reelxai"

    def generate(self, keyword: str) -> dict:
        raise DomainRecommendationProviderError(f"boom: {keyword}")


def test_generate_blueprint_uses_primary_provider_payload():
    service = DomainRecommendationService(
        provider=FakeBlueprintProvider(),
        fallback_provider=HeuristicBlueprintProvider(),
    )

    result = service.generate_blueprint("travel")

    assert result.provider == "reelxai"
    assert result.fallback_used is False
    assert result.positioning == "A premium travel naming board."
    assert result.semantic_roots[0].word == "voyage"
    assert result.multilingual_roots[0].word == "viaje"
    assert result.suggested_prefixes[:3] == ["go", "smart", "nova"]
    assert result.featured_suggestions[0].name == "voyagely"


def test_generate_blueprint_falls_back_to_heuristic_provider():
    service = DomainRecommendationService(
        provider=FailingBlueprintProvider(),
        fallback_provider=HeuristicBlueprintProvider(),
    )

    result = service.generate_blueprint("audio")

    assert result.provider == "heuristic"
    assert result.fallback_used is True
    assert len(result.semantic_roots) >= 6
    assert len(result.multilingual_roots) >= 3
    assert len(result.suggested_prefixes) == 16
    assert len(result.suggested_suffixes) == 40
    assert len(result.featured_suggestions) == 9
