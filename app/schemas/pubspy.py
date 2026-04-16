from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator


_PUB_ID_DIGITS_MIN = 10
_PUB_ID_DIGITS_MAX = 16


def normalize_domain_input(value: str) -> str:
    candidate = (value or "").strip().lower()
    if not candidate:
        raise ValueError("A domain or URL is required.")
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    parsed = urlparse(candidate)
    host = (parsed.netloc or parsed.path).strip().lower()
    host = host.split("/", 1)[0].split(":", 1)[0]
    if not host or "." not in host:
        raise ValueError("A valid domain or URL is required.")
    return candidate


def normalize_pub_id_value(value: str) -> str:
    raw = (value or "").strip().lower()
    if not raw:
        raise ValueError("A publisher ID is required.")

    prefixes = ("ca-pub-", "pub-", "host-pub-", "partner-pub-")
    digits = raw
    for prefix in prefixes:
        if raw.startswith(prefix):
            digits = raw[len(prefix) :]
            break

    if not digits.isdigit() or not (_PUB_ID_DIGITS_MIN <= len(digits) <= _PUB_ID_DIGITS_MAX):
        raise ValueError("Publisher ID must look like 'pub-1234567890'.")
    return f"pub-{digits}"


class PubSpyTrafficResult(BaseModel):
    domain: str
    status: Literal["success", "no_data", "error", "auth_error", "retryable_error"]
    formatted: str | None = None
    monthly_visits: int | None = None
    traffic_month: str | None = None
    source: str | None = None


class PubSpyWhoisSummary(BaseModel):
    registrar: str | None = None
    created_date: str | None = None
    expires_date: str | None = None


class PubSpyKeywordSummary(BaseModel):
    keyword: str
    volume: int | None = None
    cpc: float | None = None
    estimated_value: int | None = None


class PubSpyDomainMetric(BaseModel):
    domain: str
    is_current: bool = False
    traffic: PubSpyTrafficResult | None = None
    whois: PubSpyWhoisSummary | None = None
    top_keywords: list[PubSpyKeywordSummary] = Field(default_factory=list)


class PubSpyAdsTxtEntry(BaseModel):
    pub_id: str
    relationship: str
    raw_line: str


class PubSpyAdsTxtSummary(BaseModel):
    url: str
    found: bool
    has_google: bool = False
    matched_pub_id: str | None = None
    direct_count: int = 0
    reseller_count: int = 0
    entries: list[PubSpyAdsTxtEntry] = Field(default_factory=list)
    error: str | None = None
    error_type: str | None = None


class PubSpyOutboundDomain(BaseModel):
    domain: str
    count: int
    traffic: PubSpyTrafficResult | None = None
    whois: PubSpyWhoisSummary | None = None


class PubSpyAnalyzeRequest(BaseModel):
    url: str = Field(..., description="Target page URL or domain.")
    include_related_domains: bool = True
    include_outbound_domains: bool = True
    enrich_current_domain: bool = True
    include_top_keywords: bool = False
    max_related_domains: int = Field(default=25, ge=1, le=100)
    max_outbound_domains: int = Field(default=25, ge=1, le=100)
    keyword_collection_mode: Literal["direct", "browser"] = "browser"
    keyword_proxy: str | None = None
    keyword_timeout_seconds: int = Field(default=30, ge=5, le=120)
    keyword_browser_mode: Literal["isolated", "cdp", "persistent"] | None = None
    keyword_browser_cdp_url: str | None = None
    keyword_browser_executable_path: str | None = None
    keyword_browser_user_data_dir: str | None = None
    keyword_browser_channel: str | None = None
    keyword_browser_extension_path: str | None = None
    keyword_browser_headless: bool = True
    keyword_browser_timeout_ms: int = Field(default=30000, ge=5000, le=180000)
    keyword_browser_pre_click_wait_ms: int = Field(default=3000, ge=0, le=60000)
    keyword_browser_post_click_wait_ms: int = Field(default=8000, ge=0, le=60000)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return normalize_domain_input(value)


class PubSpyAnalyzeResponse(BaseModel):
    input_url: str
    page_url: str
    normalized_domain: str
    pub_id: str | None = None
    pub_id_display: str | None = None
    pub_id_source: Literal["html", "ads_txt"] | None = None
    ads_txt: PubSpyAdsTxtSummary
    current_domain: PubSpyDomainMetric
    related_domains: list[PubSpyDomainMetric] = Field(default_factory=list)
    outbound_domains: list[PubSpyOutboundDomain] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PubSpyRelatedDomainsRequest(BaseModel):
    pub_id: str
    current_domain: str | None = None
    max_domains: int = Field(default=25, ge=1, le=100)
    include_enrichment: bool = True

    @field_validator("pub_id")
    @classmethod
    def validate_pub_id(cls, value: str) -> str:
        return normalize_pub_id_value(value)

    @field_validator("current_domain")
    @classmethod
    def validate_current_domain(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_domain_input(value)
        parsed = urlparse(normalized)
        return (parsed.netloc or parsed.path).split(":", 1)[0].lower()


class PubSpyRelatedDomainsResponse(BaseModel):
    pub_id: str
    pub_id_display: str
    current_domain: str | None = None
    domains: list[PubSpyDomainMetric] = Field(default_factory=list)


class PubSpyDomainMetricsRequest(BaseModel):
    domains: list[str] = Field(..., min_length=1, max_length=100)

    @field_validator("domains")
    @classmethod
    def validate_domains(cls, values: list[str]) -> list[str]:
        seen: set[str] = set()
        normalized: list[str] = []
        for value in values:
            parsed = urlparse(normalize_domain_input(value))
            host = (parsed.netloc or parsed.path).split(":", 1)[0].lower()
            if host in seen:
                continue
            seen.add(host)
            normalized.append(host)
        if not normalized:
            raise ValueError("At least one valid domain is required.")
        return normalized


class PubSpyDomainMetricsResponse(BaseModel):
    domains: list[PubSpyDomainMetric] = Field(default_factory=list)
