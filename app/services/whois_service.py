from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Protocol

from app.core.config import AppSettings
from app.schemas.domain_recommendation import DomainAvailabilityResult


AVAILABLE_INDICATORS = [
    "no match",
    "not found",
    "no entries found",
    "no data found",
    "available for registration",
    "status: free",
    "no matching record",
    "domain not found",
]


class WhoisLookupClient(Protocol):
    def lookup(self, domain: str) -> Any:
        """Return raw whois data for a domain."""


class PythonWhoisLookupClient:
    def lookup(self, domain: str) -> Any:
        try:
            import whois
        except ImportError as exc:
            raise RuntimeError(
                "python-whois is not installed. Install dependencies with 'pip install -r requirements.txt'."
            ) from exc

        return whois.whois(domain)


@dataclass
class CacheEntry:
    expires_at: float
    result: DomainAvailabilityResult


@dataclass
class WhoisService:
    settings: AppSettings | None = None
    lookup_client: WhoisLookupClient | None = None
    time_fn: Callable[[], float] = field(default_factory=lambda: __import__("time").time)

    def __post_init__(self) -> None:
        if self.lookup_client is None:
            self.lookup_client = PythonWhoisLookupClient()
        self.timeout_seconds = (
            self.settings.domain_recommendation_whois_timeout_seconds if self.settings else 10
        )
        self.concurrency = self.settings.domain_recommendation_whois_concurrency if self.settings else 5
        self.cache_ttl_seconds = (
            self.settings.domain_recommendation_whois_cache_ttl_seconds if self.settings else 300
        )
        self._cache: dict[str, CacheEntry] = {}

    def check_domains(self, domains: list[str]) -> list[DomainAvailabilityResult]:
        ordered_domains = []
        seen: set[str] = set()
        for domain in domains:
            normalized = domain.strip().lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered_domains.append(normalized)

        results: dict[str, DomainAvailabilityResult] = {}
        pending: list[str] = []
        for domain in ordered_domains:
            cached = self._get_cached_result(domain)
            if cached is not None:
                results[domain] = cached
            else:
                pending.append(domain)

        if pending:
            executor = ThreadPoolExecutor(max_workers=self.concurrency)
            try:
                futures = {domain: executor.submit(self._lookup_domain, domain) for domain in pending}
                for domain in pending:
                    future = futures[domain]
                    try:
                        result = future.result(timeout=self.timeout_seconds)
                    except TimeoutError:
                        future.cancel()
                        result = DomainAvailabilityResult(domain=domain, available=False, error=True)
                    results[domain] = result
                    if not result.error:
                        self._set_cached_result(domain, result)
            finally:
                executor.shutdown(wait=False, cancel_futures=True)

        return [results[domain] for domain in ordered_domains]

    def _get_cached_result(self, domain: str) -> DomainAvailabilityResult | None:
        cached = self._cache.get(domain)
        if cached is None:
            return None
        if cached.expires_at < self.time_fn():
            self._cache.pop(domain, None)
            return None
        return cached.result

    def _set_cached_result(self, domain: str, result: DomainAvailabilityResult) -> None:
        self._cache[domain] = CacheEntry(
            expires_at=self.time_fn() + self.cache_ttl_seconds,
            result=result,
        )

    def _lookup_domain(self, domain: str) -> DomainAvailabilityResult:
        try:
            data = self.lookup_client.lookup(domain)
            return parse_whois_data(data, domain)
        except Exception as exc:
            if has_available_indicator(str(exc)):
                return DomainAvailabilityResult(domain=domain, available=True, error=False)
            return DomainAvailabilityResult(domain=domain, available=False, error=True)


def has_available_indicator(value: str) -> bool:
    text = value.lower()
    return any(indicator in text for indicator in AVAILABLE_INDICATORS)


def extract_mapping(data: Any) -> dict[str, Any]:
    if data is None:
        return {}
    if isinstance(data, dict):
        return data
    if hasattr(data, "__dict__"):
        return dict(getattr(data, "__dict__"))
    return {}


def first_present_value(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, list) and value:
            return value[0]
        if value != "":
            return value
    return None


def normalize_date_value(value: Any) -> str | None:
    candidate = first_present_value(value)
    if candidate is None:
        return None
    if isinstance(candidate, datetime):
        return candidate.isoformat()
    if isinstance(candidate, date):
        return candidate.isoformat()
    return str(candidate)


def parse_whois_data(data: Any, domain: str) -> DomainAvailabilityResult:
    if data is None:
        return DomainAvailabilityResult(domain=domain, available=True, error=False)

    mapping = extract_mapping(data)
    text_blob = " ".join(
        str(part)
        for part in [
            getattr(data, "text", None),
            mapping.get("text"),
            mapping.get("raw"),
            mapping,
        ]
        if part is not None
    )

    if has_available_indicator(text_blob):
        return DomainAvailabilityResult(domain=domain, available=True, error=False)

    registrar = first_present_value(
        mapping.get("registrar"),
        mapping.get("Registrar"),
        mapping.get("Sponsoring Registrar"),
        mapping.get("sponsoring registrar"),
    )
    created_date = normalize_date_value(
        first_present_value(
            mapping.get("creation_date"),
            mapping.get("Creation Date"),
            mapping.get("Created Date"),
            mapping.get("created"),
            mapping.get("registration_date"),
        )
    )
    expires_date = normalize_date_value(
        first_present_value(
            mapping.get("expiration_date"),
            mapping.get("Registry Expiry Date"),
            mapping.get("Expiry Date"),
            mapping.get("expires"),
            mapping.get("expiration date"),
        )
    )

    return DomainAvailabilityResult(
        domain=domain,
        available=False,
        error=False,
        registrar=str(registrar) if registrar is not None else None,
        created_date=created_date,
        expires_date=expires_date,
    )
