from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote, urljoin, urlparse

import httpx

from app.core.config import AppSettings
from app.schemas.pubspy import (
    PubSpyAdsTxtEntry,
    PubSpyAdsTxtSummary,
    PubSpyAnalyzeRequest,
    PubSpyAnalyzeResponse,
    PubSpyDomainMetric,
    PubSpyDomainMetricsRequest,
    PubSpyDomainMetricsResponse,
    PubSpyOutboundDomain,
    PubSpyRelatedDomainsRequest,
    PubSpyRelatedDomainsResponse,
    PubSpyTrafficResult,
    PubSpyWhoisSummary,
    normalize_pub_id_value,
)
from app.services.whois_service import WhoisService


PUB_ID_PATTERN = re.compile(r"\b(?:(ca|host|partner)-)?pub-(\d{10,16})\b", re.IGNORECASE)
DOMAIN_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9-]{1,63})+$", re.IGNORECASE)
HOSTIO_LINK_PATTERN = re.compile(
    r"""<a[^>]+href=["']/(?P<domain>[a-z0-9.-]+\.[a-z]{2,15})["'][^>]*rel=["']nofollow["'][^>]*>(?P<label>[^<]+)</a>""",
    re.IGNORECASE,
)
GOOGLE_ADS_TXT_EXCHANGE = "google.com"
KNOWN_SECOND_LEVEL_SUFFIXES = {
    "co.uk",
    "org.uk",
    "gov.uk",
    "ac.uk",
    "com.au",
    "net.au",
    "org.au",
    "co.nz",
    "com.br",
    "com.mx",
    "co.jp",
    "co.kr",
    "com.sg",
    "com.tr",
    "com.cn",
    "com.hk",
    "com.tw",
}


def _format_visits(value: int | None) -> str | None:
    if value is None:
        return None
    return f"{value:,}"


def _clean_domain(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.strip().lower()
    if not candidate:
        return None
    if "://" in candidate:
        parsed = urlparse(candidate)
        candidate = parsed.netloc or parsed.path
    candidate = candidate.split("/", 1)[0].split(":", 1)[0].strip(".")
    if candidate.startswith("www."):
        candidate = candidate[4:]
    if not candidate or "." not in candidate:
        return None
    if not DOMAIN_PATTERN.match(candidate):
        return None
    return candidate


def _to_registrable_domain(value: str | None) -> str | None:
    domain = _clean_domain(value)
    if domain is None:
        return None
    labels = domain.split(".")
    if len(labels) <= 2:
        return domain
    suffix = ".".join(labels[-2:])
    if suffix in KNOWN_SECOND_LEVEL_SUFFIXES and len(labels) >= 3:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def _normalize_pub_id_from_match(prefix: str | None, digits: str) -> str | None:
    normalized_prefix = (prefix or "").lower()
    if normalized_prefix in {"host", "partner"}:
        return None
    return f"pub-{digits}"


def _first_pub_id_from_text(text: str) -> str | None:
    for match in PUB_ID_PATTERN.finditer(text or ""):
        pub_id = _normalize_pub_id_from_match(match.group(1), match.group(2))
        if pub_id is not None:
            return pub_id
    return None


def _extract_nested_collections(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("domains", "results", "items", "data", "matches"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                nested = _extract_nested_collections(value)
                if nested:
                    return nested
    return []


class _OutboundLinkParser(HTMLParser):
    def __init__(self, page_url: str, current_domain: str) -> None:
        super().__init__(convert_charrefs=True)
        self.page_url = page_url
        self.current_domain = current_domain
        self.counter: Counter[str] = Counter()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for key, value in attrs:
            if key not in {"href", "src", "action", "data-href", "data-url"} or not value:
                continue
            joined = urljoin(self.page_url, value)
            parsed = urlparse(joined)
            if parsed.scheme not in {"http", "https"}:
                continue
            domain = _to_registrable_domain(parsed.netloc)
            if domain is None or domain == self.current_domain:
                continue
            self.counter[domain] += 1


@dataclass
class _CacheEntry:
    expires_at: float
    value: Any


@dataclass
class PubSpyService:
    settings: AppSettings
    whois_service: WhoisService | None = None
    client: httpx.Client | None = None
    time_fn: Callable[[], float] = field(default_factory=lambda: __import__("time").time)

    def __post_init__(self) -> None:
        self.whois_service = self.whois_service or WhoisService(self.settings)
        self.timeout_seconds = max(self.settings.pubspy_http_timeout_seconds, 1)
        self.domain_query_timeout_seconds = max(
            min(self.settings.pubspy_domain_query_timeout_seconds, self.timeout_seconds),
            1,
        )
        self.cache_ttl_seconds = max(self.settings.pubspy_cache_ttl_seconds, 1)
        self.domain_search_limit = max(self.settings.pubspy_domain_search_limit, 1)
        self.enrichment_concurrency = max(self.settings.pubspy_enrichment_concurrency, 1)
        self._traffic_cache: dict[str, _CacheEntry] = {}
        self._whois_cache: dict[str, _CacheEntry] = {}
        self._related_domains_cache: dict[str, _CacheEntry] = {}
        self._owns_client = self.client is None
        if self.client is None:
            self.client = httpx.Client(
                timeout=self.timeout_seconds,
                follow_redirects=True,
                trust_env=False,
                proxy=self.settings.pubspy_proxy_url,
                headers={"User-Agent": "adssearch-pubspy/1.0"},
            )

    def analyze(self, request: PubSpyAnalyzeRequest) -> PubSpyAnalyzeResponse:
        page_response = self.client.get(request.url)
        page_response.raise_for_status()
        page_url = str(page_response.url)
        normalized_domain = _to_registrable_domain(page_url)
        if normalized_domain is None:
            raise ValueError("Unable to determine a valid domain from the target URL.")

        html = page_response.text
        warnings: list[str] = []
        html_pub_id = _first_pub_id_from_text(html)
        ads_txt = self._fetch_ads_txt(normalized_domain)

        pub_id = html_pub_id or ads_txt.matched_pub_id
        pub_id_source = "html" if html_pub_id else "ads_txt" if ads_txt.matched_pub_id else None
        if pub_id is None:
            warnings.append("No AdSense publisher ID was found in the page HTML or ads.txt.")

        current_domain = PubSpyDomainMetric(domain=normalized_domain, is_current=True)
        if request.enrich_current_domain:
            current_domain = self.lookup_domain_metrics(
                PubSpyDomainMetricsRequest(domains=[normalized_domain])
            ).domains[0]
            current_domain.is_current = True

        related_domains: list[PubSpyDomainMetric] = []
        if pub_id and request.include_related_domains:
            related = self.related_domains(
                PubSpyRelatedDomainsRequest(
                    pub_id=pub_id,
                    current_domain=normalized_domain,
                    max_domains=request.max_related_domains,
                    include_enrichment=True,
                )
            )
            related_domains = related.domains

        outbound_domains: list[PubSpyOutboundDomain] = []
        if request.include_outbound_domains:
            outbound_domains = self._extract_outbound_domains(
                page_url=page_url,
                current_domain=normalized_domain,
                html=html,
                max_domains=request.max_outbound_domains,
            )

        return PubSpyAnalyzeResponse(
            input_url=request.url,
            page_url=page_url,
            normalized_domain=normalized_domain,
            pub_id=pub_id,
            pub_id_display=f"ca-{pub_id}" if pub_id else None,
            pub_id_source=pub_id_source,
            ads_txt=ads_txt,
            current_domain=current_domain,
            related_domains=related_domains,
            outbound_domains=outbound_domains,
            warnings=warnings,
        )

    def related_domains(self, request: PubSpyRelatedDomainsRequest) -> PubSpyRelatedDomainsResponse:
        domains = self._fetch_related_domain_names(request.pub_id)
        current_domain = _to_registrable_domain(request.current_domain)
        filtered = [
            domain
            for domain in domains
            if domain != current_domain
        ][: request.max_domains]

        metrics: list[PubSpyDomainMetric]
        if request.include_enrichment and filtered:
            metrics = self.lookup_domain_metrics(PubSpyDomainMetricsRequest(domains=filtered)).domains
        else:
            metrics = [PubSpyDomainMetric(domain=domain) for domain in filtered]

        return PubSpyRelatedDomainsResponse(
            pub_id=request.pub_id,
            pub_id_display=f"ca-{request.pub_id}",
            current_domain=current_domain,
            domains=metrics,
        )

    def lookup_domain_metrics(self, request: PubSpyDomainMetricsRequest) -> PubSpyDomainMetricsResponse:
        whois_results: dict[str, Any] = {}
        if len(request.domains) <= 1:
            whois_results = {result.domain: result for result in self.whois_service.check_domains(request.domains)}
        with ThreadPoolExecutor(max_workers=min(self.enrichment_concurrency, len(request.domains))) as executor:
            futures = {
                domain: executor.submit(self._build_domain_metric, domain, whois_results.get(domain))
                for domain in request.domains
            }
        return PubSpyDomainMetricsResponse(domains=[futures[domain].result() for domain in request.domains])

    def _build_domain_metric(self, domain: str, whois_result: Any) -> PubSpyDomainMetric:
        traffic = self._lookup_domain_traffic(domain)
        whois_summary = self._build_whois_summary(domain, whois_result)
        return PubSpyDomainMetric(
            domain=domain,
            traffic=traffic,
            whois=whois_summary,
        )

    def _fetch_ads_txt(self, domain: str) -> PubSpyAdsTxtSummary:
        url = f"https://{domain}/ads.txt"
        try:
            response = self.client.get(url)
        except httpx.HTTPError as exc:
            return PubSpyAdsTxtSummary(
                url=url,
                found=False,
                error=str(exc),
                error_type="request_error",
            )

        if response.status_code == 404:
            return PubSpyAdsTxtSummary(url=url, found=False, error_type="not_found")
        if response.status_code >= 400:
            return PubSpyAdsTxtSummary(
                url=url,
                found=False,
                error=f"HTTP {response.status_code}",
                error_type="http_error",
            )

        entries: list[PubSpyAdsTxtEntry] = []
        direct_count = 0
        reseller_count = 0
        matched_pub_id: str | None = None

        for raw_line in response.text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            canonical = line.split("#", 1)[0].strip()
            parts = [part.strip() for part in canonical.split(",")]
            if len(parts) < 3:
                continue
            exchange = parts[0].lower()
            if exchange != GOOGLE_ADS_TXT_EXCHANGE:
                continue
            try:
                pub_id = normalize_pub_id_value(parts[1])
            except ValueError:
                continue
            relationship = parts[2].upper()
            entries.append(
                PubSpyAdsTxtEntry(
                    pub_id=pub_id,
                    relationship=relationship,
                    raw_line=line,
                )
            )
            if relationship == "DIRECT":
                direct_count += 1
            elif relationship == "RESELLER":
                reseller_count += 1
            if matched_pub_id is None:
                matched_pub_id = pub_id

        return PubSpyAdsTxtSummary(
            url=url,
            found=True,
            has_google=bool(entries),
            matched_pub_id=matched_pub_id,
            direct_count=direct_count,
            reseller_count=reseller_count,
            entries=entries,
        )

    def _extract_outbound_domains(
        self,
        page_url: str,
        current_domain: str,
        html: str,
        max_domains: int,
    ) -> list[PubSpyOutboundDomain]:
        parser = _OutboundLinkParser(page_url=page_url, current_domain=current_domain)
        parser.feed(html or "")
        top_domains = sorted(parser.counter.items(), key=lambda item: (-item[1], item[0]))[:max_domains]
        if not top_domains:
            return []

        enrichment = {
            item.domain: item
            for item in self.lookup_domain_metrics(
                PubSpyDomainMetricsRequest(domains=[domain for domain, _ in top_domains])
            ).domains
        }
        return [
            PubSpyOutboundDomain(
                domain=domain,
                count=count,
                traffic=enrichment.get(domain).traffic if enrichment.get(domain) else None,
                whois=enrichment.get(domain).whois if enrichment.get(domain) else None,
            )
            for domain, count in top_domains
        ]

    def _lookup_domain_traffic(self, domain: str) -> PubSpyTrafficResult:
        cached = self._get_cache(self._traffic_cache, domain)
        if cached is not None:
            return cached

        traffic_url = f"{self.settings.pubspy_domain_query_base_url.rstrip('/')}/api/traffic/{quote(domain)}"
        headers = self._client_token_headers()

        result = self._request_traffic_endpoint(traffic_url, domain, source="traffic_api", headers=headers)
        if result.status not in {"auth_error", "success"}:
            fallback_url = (
                f"{self.settings.pubspy_domain_query_base_url.rstrip('/')}/api/domains"
                f"?search={quote(domain)}&limit={self.domain_search_limit}"
            )
            fallback = self._request_domain_search_endpoint(fallback_url, domain, headers=headers)
            if fallback.status == "success":
                result = fallback
            elif result.status == "no_data":
                result = fallback

        self._set_cache(self._traffic_cache, domain, result)
        return result

    def _build_whois_summary(self, domain: str, whois_result: Any) -> PubSpyWhoisSummary | None:
        local_summary = None
        if whois_result is not None:
            local_summary = PubSpyWhoisSummary(
                registrar=whois_result.registrar,
                created_date=whois_result.created_date,
                expires_date=whois_result.expires_date,
            )
        if local_summary and any(
            [local_summary.registrar, local_summary.created_date, local_summary.expires_date]
        ):
            return local_summary
        return self._lookup_worker_whois(domain) or local_summary

    def _lookup_worker_whois(self, domain: str) -> PubSpyWhoisSummary | None:
        cached = self._get_cache(self._whois_cache, domain)
        if cached is not None:
            return cached

        url = f"{self.settings.pubspy_domain_query_base_url.rstrip('/')}/api/whois?domain={quote(domain)}"
        try:
            response = self.client.get(
                url,
                headers=self._client_token_headers(),
                timeout=self.domain_query_timeout_seconds,
            )
        except httpx.HTTPError:
            self._set_cache(self._whois_cache, domain, None)
            return None

        if response.status_code in {401, 403, 404} or response.status_code >= 400:
            self._set_cache(self._whois_cache, domain, None)
            return None

        summary = self._extract_whois_summary_from_payload(self._safe_json(response))
        self._set_cache(self._whois_cache, domain, summary)
        return summary

    def _request_traffic_endpoint(
        self,
        url: str,
        domain: str,
        source: str,
        headers: dict[str, str],
    ) -> PubSpyTrafficResult:
        try:
            response = self.client.get(url, headers=headers, timeout=self.domain_query_timeout_seconds)
        except httpx.HTTPError:
            return PubSpyTrafficResult(domain=domain, status="error", source=source)

        if response.status_code in {401, 403}:
            return PubSpyTrafficResult(domain=domain, status="auth_error", source=source)
        if response.status_code == 404:
            return PubSpyTrafficResult(domain=domain, status="no_data", source=source)
        if response.status_code == 429 or response.status_code >= 500:
            return PubSpyTrafficResult(domain=domain, status="retryable_error", source=source)
        if response.status_code >= 400:
            return PubSpyTrafficResult(domain=domain, status="error", source=source)

        visits, traffic_month = self._extract_visits(response)
        if visits is None:
            return PubSpyTrafficResult(domain=domain, status="no_data", source=source)
        return PubSpyTrafficResult(
            domain=domain,
            status="success",
            formatted=_format_visits(visits),
            monthly_visits=visits,
            traffic_month=traffic_month,
            source=source,
        )

    def _request_domain_search_endpoint(
        self,
        url: str,
        domain: str,
        headers: dict[str, str],
    ) -> PubSpyTrafficResult:
        try:
            response = self.client.get(url, headers=headers, timeout=self.domain_query_timeout_seconds)
        except httpx.HTTPError:
            return PubSpyTrafficResult(domain=domain, status="error", source="domain_search")

        if response.status_code in {401, 403}:
            return PubSpyTrafficResult(domain=domain, status="auth_error", source="domain_search")
        if response.status_code == 404:
            return PubSpyTrafficResult(domain=domain, status="no_data", source="domain_search")
        if response.status_code == 429 or response.status_code >= 500:
            return PubSpyTrafficResult(domain=domain, status="retryable_error", source="domain_search")
        if response.status_code >= 400:
            return PubSpyTrafficResult(domain=domain, status="error", source="domain_search")

        payload = self._safe_json(response)
        match = self._find_domain_match(payload, domain)
        if match is None:
            return PubSpyTrafficResult(domain=domain, status="no_data", source="domain_search")

        visits, traffic_month = self._extract_visits_from_payload(match)
        if visits is None:
            return PubSpyTrafficResult(domain=domain, status="no_data", source="domain_search")
        return PubSpyTrafficResult(
            domain=domain,
            status="success",
            formatted=_format_visits(visits),
            monthly_visits=visits,
            traffic_month=traffic_month,
            source="domain_search",
        )

    def _fetch_related_domain_names(self, pub_id: str) -> list[str]:
        cached = self._get_cache(self._related_domains_cache, pub_id)
        if cached is not None:
            return cached

        url = f"{self.settings.pubspy_hostio_base_url.rstrip('/')}/{quote(pub_id)}"
        try:
            response = self.client.get(url)
        except httpx.HTTPError:
            self._set_cache(self._related_domains_cache, pub_id, [])
            return []

        if response.status_code >= 500:
            self._set_cache(self._related_domains_cache, pub_id, [])
            return []

        collected: list[str] = []
        seen: set[str] = set()
        for item in self._extract_related_candidates(self._safe_json(response)):
            domain = _to_registrable_domain(item)
            if domain is None or domain in seen:
                continue
            seen.add(domain)
            collected.append(domain)

        if not collected:
            for item in self._extract_related_domains_from_html(response.text):
                domain = _to_registrable_domain(item)
                if domain is None or domain in seen:
                    continue
                seen.add(domain)
                collected.append(domain)

        self._set_cache(self._related_domains_cache, pub_id, collected)
        return collected

    def _extract_related_candidates(self, payload: Any) -> list[str]:
        if isinstance(payload, str):
            return [payload]
        if isinstance(payload, list):
            values: list[str] = []
            for item in payload:
                values.extend(self._extract_related_candidates(item))
            return values
        if isinstance(payload, dict):
            values: list[str] = []
            for key in ("domain", "name", "hostname"):
                value = payload.get(key)
                if isinstance(value, str):
                    values.append(value)
            for key in ("domains", "results", "items", "data"):
                value = payload.get(key)
                if isinstance(value, (list, dict, str)):
                    values.extend(self._extract_related_candidates(value))
            return values
        return []

    def _extract_related_domains_from_html(self, html: str) -> list[str]:
        values: list[str] = []
        seen: set[str] = set()
        for match in HOSTIO_LINK_PATTERN.finditer(html or ""):
            domain = (match.group("domain") or "").strip().lower()
            label = (match.group("label") or "").strip().lower()
            candidate = domain if DOMAIN_PATTERN.match(domain) else label if DOMAIN_PATTERN.match(label) else ""
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            values.append(candidate)
        return values

    def _find_domain_match(self, payload: Any, domain: str) -> dict[str, Any] | None:
        collections = _extract_nested_collections(payload)
        if not collections and isinstance(payload, list):
            collections = payload
        candidates = [payload] if isinstance(payload, dict) else []
        candidates.extend(item for item in collections if isinstance(item, dict))

        for item in candidates:
            domain_value = _to_registrable_domain(item.get("domain") or item.get("hostname") or item.get("name"))
            if domain_value == domain:
                return item
        return None

    def _extract_visits(self, response: httpx.Response) -> tuple[int | None, str | None]:
        payload = self._safe_json(response)
        return self._extract_visits_from_payload(payload)

    def _extract_visits_from_payload(self, payload: Any) -> tuple[int | None, str | None]:
        if not isinstance(payload, dict):
            return None, None

        direct_candidates = [
            payload.get("monthly_visits"),
            payload.get("monthlyVisits"),
            payload.get("visits"),
        ]
        data = payload.get("data")
        if isinstance(data, dict):
            direct_candidates.extend(
                [
                    data.get("monthly_visits"),
                    data.get("monthlyVisits"),
                    data.get("visits"),
                ]
            )
        for candidate in direct_candidates:
            visits = self._coerce_int(candidate)
            if visits is not None:
                traffic_month = (
                    payload.get("traffic_month")
                    or payload.get("month")
                    or (data.get("traffic_month") if isinstance(data, dict) else None)
                    or (data.get("month") if isinstance(data, dict) else None)
                )
                return visits, str(traffic_month) if traffic_month else None

        traffic_series = None
        if isinstance(data, dict):
            traffic_series = data.get("traffic")
        if traffic_series is None:
            traffic_series = payload.get("traffic")
        if isinstance(traffic_series, list):
            latest_visits = None
            latest_month = None
            for entry in traffic_series:
                if not isinstance(entry, dict):
                    continue
                visits = self._coerce_int(
                    entry.get("monthly_visits") or entry.get("monthlyVisits") or entry.get("visits")
                )
                if visits is None:
                    continue
                latest_visits = visits
                latest_month = entry.get("month") or entry.get("traffic_month")
            return latest_visits, str(latest_month) if latest_month else None
        if isinstance(traffic_series, dict):
            latest_month = None
            latest_visits = None
            for month, raw_visits in sorted(traffic_series.items()):
                visits = self._coerce_int(raw_visits)
                if visits is None:
                    continue
                latest_month = month
                latest_visits = visits
            return latest_visits, str(latest_month) if latest_month else None
        return None, None

    def _extract_whois_summary_from_payload(self, payload: Any) -> PubSpyWhoisSummary | None:
        if not isinstance(payload, dict):
            return None

        parsed = payload.get("parsed")
        if not isinstance(parsed, dict):
            data = payload.get("data")
            if isinstance(data, list) and data and isinstance(data[0], dict):
                parsed = data[0]
            elif isinstance(data, dict):
                parsed = data
            else:
                parsed = payload

        registrar = parsed.get("registrar")
        created_date = (
            parsed.get("registered")
            or parsed.get("created")
            or parsed.get("created_date")
            or parsed.get("creation_date")
        )
        expires_date = (
            parsed.get("expires")
            or parsed.get("expires_date")
            or parsed.get("expiration_date")
        )

        if not any([registrar, created_date, expires_date]):
            return None
        return PubSpyWhoisSummary(
            registrar=str(registrar) if registrar else None,
            created_date=str(created_date) if created_date else None,
            expires_date=str(expires_date) if expires_date else None,
        )

    def _coerce_int(self, value: Any) -> int | None:
        if value is None or value == "":
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            digits = value.replace(",", "").strip()
            if digits.isdigit():
                return int(digits)
        return None

    def _safe_json(self, response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return {}

    def _client_token_headers(self) -> dict[str, str]:
        if not self.settings.pubspy_client_token:
            return {}
        return {"X-Client-Token": self.settings.pubspy_client_token}

    def _get_cache(self, store: dict[str, _CacheEntry], key: str) -> Any | None:
        cached = store.get(key)
        if cached is None:
            return None
        if cached.expires_at < self.time_fn():
            store.pop(key, None)
            return None
        return cached.value

    def _set_cache(self, store: dict[str, _CacheEntry], key: str, value: Any) -> None:
        store[key] = _CacheEntry(expires_at=self.time_fn() + self.cache_ttl_seconds, value=value)
