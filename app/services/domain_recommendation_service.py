from __future__ import annotations

import json
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.core.config import AppSettings

from app.schemas.domain_recommendation import (
    AffixCandidateGroups,
    CandidateMethod,
    DigitCandidateGroups,
    DomainCandidate,
    DomainRecommendationBlueprint,
    DomainRecommendationCandidatesRequest,
    DomainRecommendationCandidatesResponse,
    DomainScoreBreakdown,
    FeaturedDomainSuggestion,
    LetterCandidateGroups,
    RecommendationRoot,
)


PREFIX_LIBRARY = [
    "ai",
    "go",
    "get",
    "open",
    "smart",
    "super",
    "nova",
    "forge",
    "build",
    "dev",
    "tech",
    "code",
    "data",
    "byte",
    "spark",
    "fast",
    "pro",
    "ez",
    "studio",
    "ultra",
    "easy",
    "try",
    "run",
    "now",
    "launch",
    "craft",
    "one",
    "top",
    "net",
    "sys",
    "prime",
]

CURATED_SUFFIX_LIBRARY_GROUPS = [
    ["ai", "auto", "smart", "intelli", "omni", "neo", "next", "hyper", "ultra", "meta"],
    ["create", "craft", "make", "gen", "prompt", "idea", "dream", "muse", "magic", "spark"],
    ["beat", "tune", "song", "melody", "rhythm", "groove", "loop", "riff", "audio", "sound"],
    ["voice", "vox", "echo", "speak", "talk", "say", "dub", "call", "speech", "tone"],
    ["vid", "video", "clip", "reel", "frame", "scene", "motion", "visual", "view", "lens"],
    ["image", "pixel", "canvas", "render", "style", "art", "photo", "color", "design", "sketch"],
    ["data", "flow", "sync", "link", "route", "chain", "stack", "grid", "stream", "ops"],
    ["core", "engine", "cloud", "node", "api", "dev", "code", "script", "bot", "agent"],
    ["launch", "boost", "scale", "growth", "sales", "market", "brand", "convert", "revenue", "lead"],
    ["nova", "flux", "quantum", "orbit", "prism", "atlas", "pulse", "signal", "vector", "shift"],
]

LEGACY_SUFFIX_LIBRARY = [
    "forge",
    "mint",
    "maker",
    "build",
    "smith",
    "lab",
    "studio",
    "factory",
    "drive",
    "pilot",
    "bridge",
    "lift",
    "rise",
    "turbo",
    "dash",
    "jump",
    "fly",
    "os",
    "base",
    "layer",
    "hub",
    "assist",
    "copilot",
    "mate",
    "desk",
    "rep",
    "guide",
    "buddy",
    "operator",
    "wave",
    "cast",
    "works",
    "one",
    "hq",
    "pro",
    "suite",
    "systems",
    "platform",
    "enterprise",
    "ly",
    "ify",
    "io",
    "sy",
    "iq",
    "matic",
    "verse",
    "deck",
    "space",
    "plus",
    "prime",
    "max",
    "pad",
    "dock",
    "port",
    "zone",
    "box",
    "app",
    "kit",
    "vault",
]

LETTERS = list("abcdefghijklmnopqrstuvwxyz")
PROTECTED_BRAND_TOKENS = [
    "google",
    "apple",
    "microsoft",
    "openai",
    "meta",
    "amazon",
    "tesla",
    "tripadvisor",
]
SCORE_WEIGHTS = {
    "memorability": 0.25,
    "pronunciation": 0.2,
    "brand_safety": 0.2,
    "seo": 0.2,
    "investment": 0.15,
}

SUFFIX_LIBRARY = list(
    dict.fromkeys(
        value
        for index in range(max(len(group) for group in CURATED_SUFFIX_LIBRARY_GROUPS))
        for group in CURATED_SUFFIX_LIBRARY_GROUPS
        for value in ([group[index]] if index < len(group) else [])
    )
)
for suffix in LEGACY_SUFFIX_LIBRARY:
    if suffix not in SUFFIX_LIBRARY:
        SUFFIX_LIBRARY.append(suffix)

PREFIX_FALLBACK_COUNT = 16
SUFFIX_FALLBACK_COUNT = 40
PREFIX_SUGGESTION_LIMIT = 16
SUFFIX_SUGGESTION_LIMIT = 40
FEATURED_SUGGESTION_LIMIT = 9

THEME_ALIASES = {
    "travel": {"travel", "trip", "tour", "flight", "hotel", "vacation", "journey"},
    "audio": {"audio", "music", "podcast", "voice", "sound", "beat"},
    "agent": {"agent", "ai", "assistant", "automation", "bot", "copilot", "workflow"},
    "video": {"video", "clip", "reel", "film", "stream", "motion"},
    "image": {"image", "photo", "design", "art", "visual", "render"},
    "finance": {"finance", "money", "bank", "fund", "wealth", "crypto", "invest"},
    "commerce": {"shop", "store", "buy", "cart", "market", "retail", "commerce"},
}

SEMANTIC_ROOT_LIBRARY = {
    "travel": ["voyage", "roam", "atlas", "route", "trek", "escape", "globe", "path", "nomad", "journey"],
    "audio": ["beat", "tune", "echo", "voice", "sound", "tone", "mix", "groove", "wave", "vox"],
    "agent": ["assist", "pilot", "guide", "ops", "flow", "task", "bot", "logic", "desk", "auto"],
    "video": ["reel", "frame", "scene", "motion", "lens", "view", "clip", "visual", "stream", "edit"],
    "image": ["pixel", "canvas", "render", "style", "photo", "design", "art", "sketch", "color", "frame"],
    "finance": ["fund", "ledger", "yield", "asset", "vault", "capital", "signal", "trade", "wealth", "bank"],
    "commerce": ["store", "cart", "shelf", "brand", "market", "deal", "sale", "supply", "retail", "buy"],
    "generic": ["forge", "spark", "atlas", "signal", "pilot", "path", "base", "shift", "prime", "nova"],
}

MULTILINGUAL_ROOT_LIBRARY = {
    "travel": [
        {"word": "viaje", "language": "Spanish", "category": "Translation", "note": "Latin-script travel cue"},
        {"word": "voyage", "language": "French", "category": "Translation", "note": "Travel-inspired root"},
        {"word": "reise", "language": "German", "category": "Translation", "note": "Short trip-related cue"},
        {"word": "viaggio", "language": "Italian", "category": "Translation", "note": "Romance-language variant"},
    ],
    "audio": [
        {"word": "sonido", "language": "Spanish", "category": "Translation", "note": "Sound-oriented cue"},
        {"word": "voce", "language": "Italian", "category": "Translation", "note": "Voice-inspired root"},
        {"word": "musica", "language": "Spanish", "category": "Translation", "note": "Music-adjacent root"},
        {"word": "klang", "language": "German", "category": "Translation", "note": "Sound-inspired cue"},
    ],
    "agent": [
        {"word": "agente", "language": "Spanish", "category": "Translation", "note": "Agent keyword translation"},
        {"word": "guida", "language": "Italian", "category": "Translation", "note": "Guide-inspired root"},
        {"word": "copiloto", "language": "Spanish", "category": "Translation", "note": "Copilot-style cue"},
        {"word": "assistente", "language": "Italian", "category": "Translation", "note": "Assistant-inspired variant"},
    ],
    "video": [
        {"word": "video", "language": "Spanish", "category": "Translation", "note": "Universal video root"},
        {"word": "cine", "language": "Spanish", "category": "Translation", "note": "Cinema-inspired cue"},
        {"word": "vista", "language": "Spanish", "category": "Translation", "note": "Visual perspective cue"},
        {"word": "scena", "language": "Italian", "category": "Translation", "note": "Scene-inspired root"},
    ],
    "image": [
        {"word": "imagen", "language": "Spanish", "category": "Translation", "note": "Image keyword translation"},
        {"word": "foto", "language": "Italian", "category": "Translation", "note": "Photo-inspired short root"},
        {"word": "arte", "language": "Spanish", "category": "Translation", "note": "Art-oriented cue"},
        {"word": "colore", "language": "Italian", "category": "Translation", "note": "Color-inspired root"},
    ],
    "finance": [
        {"word": "dinero", "language": "Spanish", "category": "Translation", "note": "Money-related cue"},
        {"word": "banca", "language": "Italian", "category": "Translation", "note": "Banking-oriented root"},
        {"word": "valor", "language": "Spanish", "category": "Translation", "note": "Value-oriented cue"},
        {"word": "saldo", "language": "Spanish", "category": "Translation", "note": "Balance-related root"},
    ],
    "commerce": [
        {"word": "mercado", "language": "Spanish", "category": "Translation", "note": "Market-oriented root"},
        {"word": "tienda", "language": "Spanish", "category": "Translation", "note": "Store keyword translation"},
        {"word": "negozio", "language": "Italian", "category": "Translation", "note": "Shop-oriented cue"},
        {"word": "venta", "language": "Spanish", "category": "Translation", "note": "Sale-oriented root"},
    ],
    "generic": [
        {"word": "terra", "language": "Latin-inspired", "category": "Cross-language cue", "note": "Global naming cue"},
        {"word": "mundo", "language": "Spanish", "category": "Cross-language cue", "note": "World-oriented cue"},
        {"word": "viva", "language": "Romance-inspired", "category": "Cross-language cue", "note": "Positive naming cue"},
        {"word": "modo", "language": "Italian", "category": "Cross-language cue", "note": "Mode-oriented short root"},
    ],
}


def clamp(value: float, minimum: float = 1.0, maximum: float = 10.0) -> float:
    return max(minimum, min(maximum, value))


def round_score(value: float) -> float:
    return round(value * 10.0) / 10.0


def sanitize_recommendation_token(value: str, max_length: int = 18) -> str:
    return (
        re.sub(r"^-+|-+$", "", re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9-]", "", re.sub(r"\..*$", "", value.lower().strip()))))
        [:max_length]
        .strip("-")
    )


def to_display_label(root: RecommendationRoot) -> str:
    return f"{root.word} · {root.language}" if root.language else root.word


def has_protected_brand_token(name: str) -> bool:
    return any(token in name for token in PROTECTED_BRAND_TOKENS)


def count_syllable_hints(name: str) -> int:
    return len(re.findall(r"[aeiouy]+", name))


def max_consonant_cluster(name: str) -> int:
    clusters = re.findall(r"[bcdfghjklmnpqrstvwxyz]{2,}", name)
    return max((len(cluster) for cluster in clusters), default=0)


def calculate_domain_score(name: str, keyword: str) -> DomainScoreBreakdown:
    normalized = sanitize_recommendation_token(name, 32)
    length = len(normalized)
    vowels = len(re.findall(r"[aeiouy]", normalized))
    vowel_ratio = (vowels / length) if length > 0 else 0.0
    syllable_hints = count_syllable_hints(normalized)
    consonant_cluster = max_consonant_cluster(normalized)
    has_digit = any(char.isdigit() for char in normalized)
    has_hyphen = "-" in normalized
    keyword_included = keyword in normalized
    protected_penalty = 2.8 if has_protected_brand_token(normalized) else 0.0

    memorability = clamp(
        8.9
        - abs(length - 10) * 0.28
        - (1.1 if has_digit else 0.0)
        - (0.6 if has_hyphen else 0.0)
        + (0.4 if keyword_included else 0.0)
    )
    pronunciation = clamp(
        8.7
        - abs(vowel_ratio - 0.42) * 7
        - max(0, consonant_cluster - 3) * 0.8
        - max(0, syllable_hints - 4) * 0.3
    )
    brand_safety = clamp(9.1 - protected_penalty - (0.5 if has_digit else 0.0) - (0.4 if has_hyphen else 0.0))
    seo = clamp(
        6.2
        + (2.1 if keyword_included else 0.0)
        + (0.6 if normalized.startswith(keyword) or normalized.endswith(keyword) else 0.0)
    )
    investment = clamp(
        8.5
        - max(0, length - 12) * 0.22
        - (0.7 if has_digit else 0.0)
        - (0.5 if has_hyphen else 0.0)
        + (0.3 if keyword_included else 0.0)
    )

    total = round_score(
        memorability * SCORE_WEIGHTS["memorability"]
        + pronunciation * SCORE_WEIGHTS["pronunciation"]
        + brand_safety * SCORE_WEIGHTS["brand_safety"]
        + seo * SCORE_WEIGHTS["seo"]
        + investment * SCORE_WEIGHTS["investment"]
    )
    return DomainScoreBreakdown(
        memorability=round_score(memorability),
        pronunciation=round_score(pronunciation),
        brand_safety=round_score(brand_safety),
        seo=round_score(seo),
        investment=round_score(investment),
        total=total,
    )


def create_candidate(
    *,
    method: CandidateMethod,
    group: str,
    name: str,
    reason: str,
    keyword: str,
    tld: str,
) -> DomainCandidate:
    return DomainCandidate(
        method=method,
        group=group,
        name=name,
        tld=tld,
        full_domain=f"{name}.{tld}",
        reason=reason,
        score=calculate_domain_score(name, keyword),
    )


def dedupe_candidates(candidates: Iterable[DomainCandidate]) -> list[DomainCandidate]:
    seen: set[str] = set()
    result: list[DomainCandidate] = []
    for candidate in candidates:
        key = candidate.full_domain.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return result


def sort_candidates(candidates: Iterable[DomainCandidate]) -> list[DomainCandidate]:
    return dedupe_candidates(sorted(candidates, key=lambda item: item.score.total, reverse=True))


def pick_top_candidates(candidates: Iterable[DomainCandidate], count: int = 12) -> list[DomainCandidate]:
    return sort_candidates(candidates)[:count]


def build_featured_candidates(suggestions: list[FeaturedDomainSuggestion], keyword: str) -> list[DomainCandidate]:
    return sort_candidates(
        create_candidate(
            method="featured",
            group="AI highlighted",
            name=suggestion.name,
            reason=suggestion.reason,
            keyword=keyword,
            tld=suggestion.tld,
        )
        for suggestion in suggestions
    )


def build_digit_candidates(root: str, keyword: str, tld: str) -> DigitCandidateGroups:
    prefix = [
        create_candidate(
            method="digits",
            group="Digit in front",
            name=f"{index}{root}",
            reason="Numeric prefix creates a sharper, startup-like variation.",
            keyword=keyword,
            tld=tld,
        )
        for index in range(10)
    ]
    suffix = [
        create_candidate(
            method="digits",
            group="Digit at the end",
            name=f"{root}{index}",
            reason="Numeric suffix keeps the root readable while widening options.",
            keyword=keyword,
            tld=tld,
        )
        for index in range(10)
    ]
    return DigitCandidateGroups(prefix=pick_top_candidates(prefix, 10), suffix=pick_top_candidates(suffix, 10))


def build_letter_candidates(root: str, keyword: str, tld: str) -> LetterCandidateGroups:
    single_prefix = [
        create_candidate(
            method="letters",
            group="Single letter in front",
            name=f"{letter}{root}",
            reason="Adds a minimal brand hook ahead of the root.",
            keyword=keyword,
            tld=tld,
        )
        for letter in LETTERS
    ]
    single_suffix = [
        create_candidate(
            method="letters",
            group="Single letter at the end",
            name=f"{root}{letter}",
            reason="Keeps the root dominant while opening simpler brand variants.",
            keyword=keyword,
            tld=tld,
        )
        for letter in LETTERS
    ]

    double_prefix: list[DomainCandidate] = []
    double_suffix: list[DomainCandidate] = []
    for first in LETTERS:
        for second in LETTERS:
            double_prefix.append(
                create_candidate(
                    method="letters",
                    group="Double letters in front",
                    name=f"{first}{second}{root}",
                    reason="Creates more ownable combinations without leaving the root.",
                    keyword=keyword,
                    tld=tld,
                )
            )
            double_suffix.append(
                create_candidate(
                    method="letters",
                    group="Double letters at the end",
                    name=f"{root}{first}{second}",
                    reason="Extends the root into a larger naming space for exploration.",
                    keyword=keyword,
                    tld=tld,
                )
            )

    return LetterCandidateGroups(
        single_prefix=sort_candidates(single_prefix),
        single_suffix=sort_candidates(single_suffix),
        double_prefix=sort_candidates(double_prefix),
        double_suffix=sort_candidates(double_suffix),
    )


def build_affix_candidates(
    *,
    root: str,
    keyword: str,
    tld: str,
    prefixes: list[str],
    suffixes: list[str],
) -> AffixCandidateGroups:
    normalized_prefixes = [value for value in dict.fromkeys(sanitize_recommendation_token(prefix, 16) for prefix in prefixes) if value]
    normalized_suffixes = [value for value in dict.fromkeys(sanitize_recommendation_token(suffix, 16) for suffix in suffixes) if value]

    prefix_candidates = [
        create_candidate(
            method="affixes",
            group="Prefix library",
            name=f"{prefix}{root}",
            reason="Affix library expands the root with a directional brand signal.",
            keyword=keyword,
            tld=tld,
        )
        for prefix in normalized_prefixes
    ]
    suffix_candidates = [
        create_candidate(
            method="affixes",
            group="Suffix library",
            name=f"{root}{suffix}",
            reason="Suffix library pushes the root toward a clearer product story.",
            keyword=keyword,
            tld=tld,
        )
        for suffix in normalized_suffixes
    ]
    return AffixCandidateGroups(
        prefix=sort_candidates(prefix_candidates),
        suffix=sort_candidates(suffix_candidates),
    )


def merge_roots(
    seed: str,
    semantic_roots: list[RecommendationRoot],
    multilingual_roots: list[RecommendationRoot],
) -> list[RecommendationRoot]:
    roots = [
        RecommendationRoot(
            word=seed,
            label=seed,
            category="Seed keyword",
            relevance=1.0,
            kind="seed",
        ),
        *semantic_roots,
        *multilingual_roots,
    ]

    seen: set[str] = set()
    result: list[RecommendationRoot] = []
    for root in roots:
        word = sanitize_recommendation_token(root.word, 18)
        if not word or word in seen:
            continue
        seen.add(word)
        result.append(
            RecommendationRoot(
                word=word,
                label=f"{word} · {root.language}" if root.language else word,
                category=root.category,
                relevance=root.relevance,
                kind=root.kind,
                language=root.language,
                note=root.note,
            )
        )
    return result


def extract_json_candidate(text: str) -> str:
    fenced_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE)
    if fenced_match and fenced_match.group(1):
        return fenced_match.group(1).strip()

    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return text[first_brace : last_brace + 1]

    raise ValueError("AI provider returned no JSON payload.")


def parse_blueprint_payload(text: str) -> dict:
    payload = extract_json_candidate(text)
    return json.loads(payload)


def normalize_roots(values: Any, kind: str) -> list[RecommendationRoot]:
    raw_roots = values if isinstance(values, list) else []
    seen: set[str] = set()
    normalized: list[RecommendationRoot] = []
    limit = 10 if kind == "semantic" else 6

    for item in raw_roots:
        if not isinstance(item, dict):
            continue
        word = sanitize_recommendation_token(str(item.get("word", "")), 16)
        if not word or word in seen:
            continue
        seen.add(word)
        relevance = item.get("relevance", 0.72)
        if not isinstance(relevance, (int, float)):
            relevance = 0.72
        normalized.append(
            RecommendationRoot(
                word=word,
                label=f"{word} · {item.get('language')}" if item.get("language") else word,
                category=str(item.get("category") or ("AI relation" if kind == "semantic" else "Language")),
                relevance=max(0.4, min(1.0, float(relevance))),
                kind=kind,  # type: ignore[arg-type]
                language=item.get("language"),
                note=item.get("note"),
            )
        )
        if len(normalized) >= limit:
            break
    return normalized


def normalize_affixes(values: Any, fallback: list[str], limit: int) -> list[str]:
    source = values if isinstance(values, list) else []
    normalized = [
        token
        for token in (sanitize_recommendation_token(str(value), 14) for value in source)
        if token
    ]
    merged = list(dict.fromkeys([*normalized, *fallback]))
    return merged[:limit]


def normalize_insights(values: Any) -> list[str]:
    source = values if isinstance(values, list) else []
    normalized = [str(value).strip() for value in source if str(value).strip()]
    return normalized[:3]


def tokenize_keyword(keyword: str) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9]+", keyword.lower()) if token]


def resolve_theme(keyword: str) -> str:
    tokens = tokenize_keyword(keyword)
    for token in tokens or [keyword]:
        for theme, aliases in THEME_ALIASES.items():
            if token in aliases:
                return theme
    return "generic"


def build_prompt(keyword: str) -> str:
    return (
        "You are an AI naming strategist building a domain recommendation blueprint.\n\n"
        "Return ONLY valid JSON with keys positioning, insights, semanticRoots, multilingualRoots, "
        "suggestedPrefixes, suggestedSuffixes.\n"
        f'The keyword is "{keyword}".\n'
        "All words must be lowercase ASCII suitable for domains.\n"
        "semanticRoots should contain 8 to 10 items.\n"
        "multilingualRoots should contain 4 to 6 ASCII transliterations when possible.\n"
        "suggestedPrefixes should contain 10 to 12 items.\n"
        "suggestedSuffixes should contain 20 to 24 items.\n"
        "Keep insights short and concrete."
    )


def build_semantic_root_payload(keyword: str) -> list[dict[str, Any]]:
    theme = resolve_theme(keyword)
    roots = SEMANTIC_ROOT_LIBRARY.get(theme, SEMANTIC_ROOT_LIBRARY["generic"])
    tokens = tokenize_keyword(keyword)
    candidates = [*tokens, *roots]
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, root in enumerate(candidates):
        cleaned = sanitize_recommendation_token(root, 16)
        if not cleaned or cleaned == keyword or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(
            {
                "word": cleaned,
                "category": "Adjacent concept" if index < 5 else "Naming cue",
                "relevance": max(0.55, 0.94 - (index * 0.04)),
            }
        )
        if len(result) >= 10:
            break
    return result


def build_multilingual_root_payload(keyword: str) -> list[dict[str, Any]]:
    theme = resolve_theme(keyword)
    roots = MULTILINGUAL_ROOT_LIBRARY.get(theme, MULTILINGUAL_ROOT_LIBRARY["generic"])
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(roots):
        cleaned = sanitize_recommendation_token(item["word"], 16)
        if not cleaned or cleaned == keyword or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(
            {
                "word": cleaned,
                "language": item["language"],
                "category": item["category"],
                "relevance": max(0.55, 0.86 - (index * 0.05)),
                "note": item["note"],
            }
        )
        if len(result) >= 6:
            break
    return result


def build_heuristic_featured_suggestions(
    keyword: str,
    semantic_roots: list[RecommendationRoot],
    multilingual_roots: list[RecommendationRoot],
    requested_count: int = FEATURED_SUGGESTION_LIMIT,
    tld: str = "com",
) -> list[FeaturedDomainSuggestion]:
    roots = merge_roots(keyword, semantic_roots, multilingual_roots)
    base_roots = [root.word for root in roots[:6]]
    prefixes = PREFIX_LIBRARY[:6]
    suffixes = ["lab", "hub", "forge", "studio", "pilot", "works", "base", "hq"]

    scored: list[tuple[float, str, str, str]] = []
    seen_names: set[str] = set()
    for root in base_roots:
        combinations = [
            (root, "keyword-match", f"Keeps the root direct and easy to remember around {keyword}."),
            (f"{prefixes[0]}{root}", "brandable", f"Pairs {root} with an action-led prefix for launch-ready positioning."),
            (f"{prefixes[1]}{root}", "brandable", f"Adds a concise utility cue in front of {root}."),
            (f"{root}{suffixes[0]}", "product", f"Frames {root} as a product or lab-style brand."),
            (f"{root}{suffixes[1]}", "product", f"Signals a central hub around {root}."),
            (f"{root}{suffixes[2]}", "brandable", f"Adds a maker-style suffix while keeping {root} readable."),
        ]
        for name, suggestion_type, reason in combinations:
            cleaned = sanitize_recommendation_token(name, 24)
            if not cleaned or cleaned in seen_names:
                continue
            seen_names.add(cleaned)
            score = calculate_domain_score(cleaned, keyword).total
            scored.append((score, cleaned, suggestion_type, reason))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        FeaturedDomainSuggestion(
            name=name,
            tld=tld,
            full_domain=f"{name}.{tld}",
            type=suggestion_type,
            reason=reason,
        )
        for _, name, suggestion_type, reason in scored[:requested_count]
    ]


def normalize_featured_suggestions(
    values: Any,
    fallback: list[FeaturedDomainSuggestion],
    *,
    keyword: str,
    tld: str = "com",
    limit: int = FEATURED_SUGGESTION_LIMIT,
) -> list[FeaturedDomainSuggestion]:
    source = values if isinstance(values, list) else []
    normalized: list[FeaturedDomainSuggestion] = []
    seen: set[str] = set()

    for item in source:
        if not isinstance(item, dict):
            continue
        name = sanitize_recommendation_token(str(item.get("name", "")), 24)
        if not name or name in seen:
            continue
        suggestion_tld = sanitize_recommendation_token(str(item.get("tld", tld)), 12) or tld
        full_domain = str(item.get("full_domain") or item.get("fullDomain") or f"{name}.{suggestion_tld}")
        normalized.append(
            FeaturedDomainSuggestion(
                name=name,
                tld=suggestion_tld,
                full_domain=full_domain,
                type=str(item.get("type") or ("keyword-match" if keyword in name else "brandable")),
                reason=str(item.get("reason") or f"Generated around the root {name}."),
            )
        )
        seen.add(name)
        if len(normalized) >= limit:
            break

    for item in fallback:
        if item.name in seen:
            continue
        normalized.append(item)
        seen.add(item.name)
        if len(normalized) >= limit:
            break

    return normalized[:limit]


class DomainRecommendationProviderError(Exception):
    pass


class BlueprintProvider(Protocol):
    provider_name: str

    def generate(self, keyword: str) -> dict[str, Any]:
        """Return a raw blueprint payload."""


@dataclass
class HeuristicBlueprintProvider:
    provider_name: str = "heuristic"

    def generate(self, keyword: str) -> dict[str, Any]:
        theme = resolve_theme(keyword)
        return {
            "positioning": f'A focused naming board for turning "{keyword}" into clearer, more ownable domain directions.',
            "insights": [
                "Start with short, pronounceable roots before exploring larger combinations.",
                "Treat .com-ready names as the default benchmark for memorability and resale value.",
                f"Use {theme}-adjacent roots first, then widen the board with affixes and multilingual cues.",
            ],
            "semanticRoots": build_semantic_root_payload(keyword),
            "multilingualRoots": build_multilingual_root_payload(keyword),
            "suggestedPrefixes": PREFIX_LIBRARY[:12],
            "suggestedSuffixes": SUFFIX_LIBRARY[:24],
        }


@dataclass
class OpenAICompatibleBlueprintProvider:
    api_key: str | None
    model: str
    base_url: str
    timeout_seconds: int
    client: httpx.Client | None = None
    provider_name: str = "reelxai"

    def generate(self, keyword: str) -> dict[str, Any]:
        if not self.api_key:
            raise DomainRecommendationProviderError("DOMAIN_RECOMMENDATION_AI_API_KEY is not configured.")

        payload = {
            "model": self.model,
            "temperature": 0.35,
            "messages": [
                {
                    "role": "system",
                    "content": "You return strict JSON only. No markdown, no explanations.",
                },
                {
                    "role": "user",
                    "content": build_prompt(keyword),
                },
            ],
        }
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}"}

        close_client = False
        client = self.client
        if client is None:
            client = httpx.Client(timeout=self.timeout_seconds, trust_env=False)
            close_client = True

        try:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            content = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content")
            )
            if not isinstance(content, str) or not content.strip():
                raise DomainRecommendationProviderError("AI provider returned an empty blueprint response.")
            return parse_blueprint_payload(content)
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, IndexError, ValueError) as exc:
            raise DomainRecommendationProviderError(f"Failed to generate blueprint from AI provider: {exc}") from exc
        finally:
            if close_client:
                client.close()


@dataclass
class ReplicateBlueprintProvider:
    api_token: str | None
    model: str
    base_url: str
    timeout_seconds: int
    client: httpx.Client | None = None
    provider_name: str = "replicate"

    def generate(self, keyword: str) -> dict[str, Any]:
        if not self.api_token:
            raise DomainRecommendationProviderError("REPLICATE_API_TOKEN is not configured.")

        url = f"{self.base_url.rstrip('/')}/models/{self.model}/predictions"
        payload = {
            "input": {
                "prompt": build_prompt(keyword),
                "max_tokens": 1200,
                "temperature": 0.35,
                "top_p": 0.95,
            }
        }
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            "Prefer": "wait=45",
        }

        close_client = False
        client = self.client
        if client is None:
            client = httpx.Client(timeout=self.timeout_seconds, trust_env=False)
            close_client = True

        try:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            prediction = self._wait_for_prediction(client, response.json(), headers)
            output = prediction.get("output")
            if isinstance(output, list):
                text = "".join(str(item) for item in output)
            elif isinstance(output, str):
                text = output
            else:
                raise DomainRecommendationProviderError("Replicate returned no text output.")
            return parse_blueprint_payload(text)
        except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
            raise DomainRecommendationProviderError(f"Failed to generate blueprint from Replicate: {exc}") from exc
        finally:
            if close_client:
                client.close()

    def _wait_for_prediction(self, client: httpx.Client, prediction: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        current = prediction
        for _ in range(10):
            status = current.get("status")
            if status == "succeeded":
                return current
            if status in {"failed", "canceled"}:
                raise DomainRecommendationProviderError(
                    str(current.get("error") or f"Replicate prediction {status}.")
                )
            poll_url = ((current.get("urls") or {}).get("get")) if isinstance(current.get("urls"), dict) else None
            if not poll_url:
                break
            time.sleep(1.5)
            poll_response = client.get(
                poll_url,
                headers={"Authorization": headers["Authorization"]},
            )
            poll_response.raise_for_status()
            current = poll_response.json()

        status = current.get("status")
        if status != "succeeded":
            raise DomainRecommendationProviderError("Replicate prediction timed out before completion.")
        return current


@dataclass
class ProviderChainBlueprintProvider:
    providers: list[BlueprintProvider]

    @property
    def provider_name(self) -> str:
        return self.providers[0].provider_name if self.providers else "heuristic"

    def generate(self, keyword: str) -> dict[str, Any]:
        errors: list[str] = []
        for provider in self.providers:
            try:
                return provider.generate(keyword)
            except DomainRecommendationProviderError as exc:
                errors.append(f"{provider.provider_name}: {exc}")
        raise DomainRecommendationProviderError(" | ".join(errors) or "All AI providers failed.")


@dataclass
class DomainRecommendationService:
    settings: AppSettings | None = None
    provider: BlueprintProvider | None = None
    fallback_provider: BlueprintProvider | None = None

    def __post_init__(self) -> None:
        if self.provider is None:
            self.provider = self._build_provider_from_settings(self.settings)
        if self.fallback_provider is None:
            self.fallback_provider = HeuristicBlueprintProvider()

    @staticmethod
    def _build_provider_from_settings(settings: AppSettings | None) -> BlueprintProvider:
        if settings:
            provider_mode = settings.domain_recommendation_ai_provider
            if provider_mode == "heuristic":
                return HeuristicBlueprintProvider()
            if provider_mode == "reelxai":
                return OpenAICompatibleBlueprintProvider(
                    api_key=settings.domain_recommendation_reelxai_api_key,
                    model=settings.domain_recommendation_reelxai_model,
                    base_url=settings.domain_recommendation_reelxai_base_url,
                    timeout_seconds=settings.domain_recommendation_ai_timeout_seconds,
                    provider_name="reelxai",
                )
            if provider_mode == "replicate":
                return ReplicateBlueprintProvider(
                    api_token=settings.domain_recommendation_replicate_api_token,
                    model=settings.domain_recommendation_replicate_model,
                    base_url=settings.domain_recommendation_replicate_base_url,
                    timeout_seconds=settings.domain_recommendation_ai_timeout_seconds,
                )

            ai_providers: list[BlueprintProvider] = []
            if settings.domain_recommendation_reelxai_api_key:
                ai_providers.append(
                    OpenAICompatibleBlueprintProvider(
                        api_key=settings.domain_recommendation_reelxai_api_key,
                        model=settings.domain_recommendation_reelxai_model,
                        base_url=settings.domain_recommendation_reelxai_base_url,
                        timeout_seconds=settings.domain_recommendation_ai_timeout_seconds,
                        provider_name="reelxai",
                    )
                )
            if settings.domain_recommendation_replicate_api_token:
                ai_providers.append(
                    ReplicateBlueprintProvider(
                        api_token=settings.domain_recommendation_replicate_api_token,
                        model=settings.domain_recommendation_replicate_model,
                        base_url=settings.domain_recommendation_replicate_base_url,
                        timeout_seconds=settings.domain_recommendation_ai_timeout_seconds,
                    )
                )
            if ai_providers:
                return ProviderChainBlueprintProvider(ai_providers)
        return HeuristicBlueprintProvider()

    def generate_blueprint(self, keyword: str) -> DomainRecommendationBlueprint:
        fallback_used = False
        provider_name = getattr(self.provider, "provider_name", "heuristic")

        try:
            payload = self.provider.generate(keyword) if self.provider else HeuristicBlueprintProvider().generate(keyword)
        except DomainRecommendationProviderError:
            fallback_used = True
            payload = self.fallback_provider.generate(keyword) if self.fallback_provider else HeuristicBlueprintProvider().generate(keyword)
            provider_name = getattr(self.fallback_provider, "provider_name", "heuristic")

        semantic_roots = normalize_roots(payload.get("semantic_roots") or payload.get("semanticRoots"), "semantic")
        if not semantic_roots:
            semantic_roots = normalize_roots(build_semantic_root_payload(keyword), "semantic")

        multilingual_roots = normalize_roots(
            payload.get("multilingual_roots") or payload.get("multilingualRoots"),
            "multilingual",
        )
        if not multilingual_roots:
            multilingual_roots = normalize_roots(build_multilingual_root_payload(keyword), "multilingual")

        fallback_featured = build_heuristic_featured_suggestions(keyword, semantic_roots, multilingual_roots)
        featured_suggestions = normalize_featured_suggestions(
            payload.get("featured_suggestions") or payload.get("featuredSuggestions"),
            fallback_featured,
            keyword=keyword,
        )

        return DomainRecommendationBlueprint(
            keyword=keyword,
            provider=provider_name,  # type: ignore[arg-type]
            fallback_used=fallback_used,
            positioning=str(
                payload.get("positioning")
                or f'A focused naming board for turning "{keyword}" into clearer, more ownable domain directions.'
            ).strip(),
            insights=normalize_insights(payload.get("insights"))
            or [
                "Start with short, pronounceable roots before exploring larger combinations.",
                "Treat .com-ready names as the default benchmark for memorability and resale value.",
                "Use affixes and multilingual cues after validating the strongest semantic roots.",
            ],
            semantic_roots=semantic_roots,
            multilingual_roots=multilingual_roots,
            suggested_prefixes=normalize_affixes(
                payload.get("suggested_prefixes") or payload.get("suggestedPrefixes"),
                PREFIX_LIBRARY[:PREFIX_FALLBACK_COUNT],
                PREFIX_SUGGESTION_LIMIT,
            ),
            suggested_suffixes=normalize_affixes(
                payload.get("suggested_suffixes") or payload.get("suggestedSuffixes"),
                SUFFIX_LIBRARY[:SUFFIX_FALLBACK_COUNT],
                SUFFIX_SUGGESTION_LIMIT,
            ),
            featured_suggestions=featured_suggestions,
        )

    def build_candidate_board(self, request: DomainRecommendationCandidatesRequest) -> DomainRecommendationCandidatesResponse:
        featured = build_featured_candidates(request.featured_suggestions, request.keyword)[:9]
        digits = build_digit_candidates(request.root, request.keyword, request.tld)
        letters = build_letter_candidates(request.root, request.keyword, request.tld)
        affixes = build_affix_candidates(
            root=request.root,
            keyword=request.keyword,
            tld=request.tld,
            prefixes=request.suggested_prefixes,
            suffixes=request.suggested_suffixes,
        )
        overview = pick_top_candidates(
            [
                *featured,
                *digits.prefix,
                *digits.suffix,
                *letters.single_prefix,
                *letters.single_suffix,
                *letters.double_prefix,
                *letters.double_suffix,
                *affixes.prefix,
                *affixes.suffix,
            ],
            10,
        )
        total_candidates = (
            len(featured)
            + len(digits.prefix)
            + len(digits.suffix)
            + len(letters.single_prefix)
            + len(letters.single_suffix)
            + len(letters.double_prefix)
            + len(letters.double_suffix)
            + len(affixes.prefix)
            + len(affixes.suffix)
        )
        return DomainRecommendationCandidatesResponse(
            keyword=request.keyword,
            root=request.root,
            tld=request.tld,
            overview=overview,
            featured=featured,
            digits=digits,
            letters=letters,
            affixes=affixes,
            total_candidates=total_candidates,
        )
