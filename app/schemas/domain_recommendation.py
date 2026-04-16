from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator


RecommendationProvider = Literal["reelxai", "replicate", "heuristic"]
RecommendationRootKind = Literal["seed", "semantic", "multilingual"]
CandidateMethod = Literal["featured", "digits", "letters", "affixes"]

_KEYWORD_PATTERN = re.compile(r"^[a-zA-Z0-9.\s-]+$")
_ROOT_PATTERN = re.compile(r"^[a-zA-Z0-9-]+$")
_DOMAIN_PATTERN = re.compile(r"^[a-zA-Z0-9.-]+$")
_TLD_PATTERN = re.compile(r"^[a-zA-Z0-9-]+$")


class RecommendationRoot(BaseModel):
    word: str
    label: str
    category: str
    relevance: float = Field(..., ge=0.0, le=1.0)
    kind: RecommendationRootKind
    language: str | None = None
    note: str | None = None


class FeaturedDomainSuggestion(BaseModel):
    name: str
    tld: str = Field(default="com")
    full_domain: str
    type: str
    reason: str


class DomainScoreBreakdown(BaseModel):
    memorability: float
    pronunciation: float
    brand_safety: float
    seo: float
    investment: float
    total: float


class DomainCandidate(BaseModel):
    method: CandidateMethod
    group: str
    name: str
    tld: str
    full_domain: str
    reason: str
    score: DomainScoreBreakdown


class DigitCandidateGroups(BaseModel):
    prefix: list[DomainCandidate]
    suffix: list[DomainCandidate]


class LetterCandidateGroups(BaseModel):
    single_prefix: list[DomainCandidate]
    single_suffix: list[DomainCandidate]
    double_prefix: list[DomainCandidate]
    double_suffix: list[DomainCandidate]


class AffixCandidateGroups(BaseModel):
    prefix: list[DomainCandidate]
    suffix: list[DomainCandidate]


class DomainRecommendationBlueprint(BaseModel):
    keyword: str
    provider: RecommendationProvider
    fallback_used: bool
    positioning: str
    insights: list[str]
    semantic_roots: list[RecommendationRoot]
    multilingual_roots: list[RecommendationRoot]
    suggested_prefixes: list[str]
    suggested_suffixes: list[str]
    featured_suggestions: list[FeaturedDomainSuggestion]


class DomainRecommendationBlueprintRequest(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=63)

    @field_validator("keyword")
    @classmethod
    def validate_keyword(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not cleaned:
            raise ValueError("Keyword is required.")
        if not _KEYWORD_PATTERN.fullmatch(cleaned):
            raise ValueError("Only letters, numbers, spaces, dots, and hyphens are allowed.")
        return cleaned


class DomainRecommendationCandidatesRequest(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=63)
    root: str = Field(..., min_length=1, max_length=24)
    featured_suggestions: list[FeaturedDomainSuggestion] = Field(default_factory=list, max_length=24)
    suggested_prefixes: list[str] = Field(default_factory=list, max_length=64)
    suggested_suffixes: list[str] = Field(default_factory=list, max_length=96)
    tld: str = Field(default="com", min_length=2, max_length=24)

    @field_validator("keyword")
    @classmethod
    def validate_keyword(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not cleaned:
            raise ValueError("Keyword is required.")
        if not _KEYWORD_PATTERN.fullmatch(cleaned):
            raise ValueError("Only letters, numbers, spaces, dots, and hyphens are allowed.")
        return cleaned

    @field_validator("root")
    @classmethod
    def validate_root(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not cleaned:
            raise ValueError("Root is required.")
        if not _ROOT_PATTERN.fullmatch(cleaned):
            raise ValueError("Root can only contain letters, numbers, and hyphens.")
        return cleaned

    @field_validator("tld")
    @classmethod
    def validate_tld(cls, value: str) -> str:
        cleaned = value.strip().lower().lstrip(".")
        if not cleaned:
            raise ValueError("TLD is required.")
        if not _TLD_PATTERN.fullmatch(cleaned):
            raise ValueError("TLD can only contain letters, numbers, and hyphens.")
        return cleaned

    @field_validator("suggested_prefixes", "suggested_suffixes")
    @classmethod
    def normalize_affix_values(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            cleaned = value.strip().lower()
            if not cleaned:
                continue
            if not _ROOT_PATTERN.fullmatch(cleaned):
                raise ValueError("Affixes can only contain letters, numbers, and hyphens.")
            normalized.append(cleaned)
        return normalized


class DomainRecommendationCandidatesResponse(BaseModel):
    keyword: str
    root: str
    tld: str
    overview: list[DomainCandidate]
    featured: list[DomainCandidate]
    digits: DigitCandidateGroups
    letters: LetterCandidateGroups
    affixes: AffixCandidateGroups
    total_candidates: int


class DomainAvailabilityResult(BaseModel):
    domain: str
    available: bool
    error: bool = False
    registrar: str | None = None
    created_date: str | None = None
    expires_date: str | None = None


class DomainRecommendationWhoisRequest(BaseModel):
    domains: list[str] = Field(..., min_length=1, max_length=200)

    @field_validator("domains")
    @classmethod
    def validate_domains(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()

        for value in values:
            cleaned = value.strip().lower()
            if not cleaned:
                continue
            if not _DOMAIN_PATTERN.fullmatch(cleaned) or "." not in cleaned:
                raise ValueError("Each domain must be a valid domain like 'example.com'.")
            if cleaned in seen:
                continue
            seen.add(cleaned)
            normalized.append(cleaned)

        if not normalized:
            raise ValueError("At least one valid domain is required.")
        return normalized


class DomainRecommendationWhoisResponse(BaseModel):
    results: list[DomainAvailabilityResult]
