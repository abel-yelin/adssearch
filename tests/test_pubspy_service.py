import httpx

from app.core.config import AppSettings
from app.schemas.domain_recommendation import DomainAvailabilityResult
from app.schemas.pubspy import PubSpyAnalyzeRequest, PubSpyDomainMetricsRequest, PubSpyRelatedDomainsRequest
from app.services.pubspy_service import PubSpyService


class FakeWhoisService:
    def check_domains(self, domains: list[str]) -> list[DomainAvailabilityResult]:
        return [
            DomainAvailabilityResult(
                domain=domain,
                available=False,
                error=False,
                registrar="Test Registrar",
                created_date="2024-01-01T00:00:00",
                expires_date="2027-01-01T00:00:00",
            )
            for domain in domains
        ]


class EmptyWhoisService:
    def check_domains(self, domains: list[str]) -> list[DomainAvailabilityResult]:
        return [
            DomainAvailabilityResult(
                domain=domain,
                available=False,
                error=True,
                registrar=None,
                created_date=None,
                expires_date=None,
            )
            for domain in domains
        ]


def build_service(handler) -> PubSpyService:
    settings = AppSettings(
        pubspy_domain_query_base_url="https://worker.test",
        pubspy_hostio_base_url="https://host.io/adsense",
        pubspy_client_token="token-123",
        pubspy_http_timeout_seconds=5,
        pubspy_domain_search_limit=50,
        pubspy_cache_ttl_seconds=60,
    )
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    return PubSpyService(settings=settings, whois_service=FakeWhoisService(), client=client)


def test_pubspy_analyze_extracts_pub_id_related_domains_and_outbound_domains():
    html = """
    <html>
      <body>
        <script>window.adsbygoogle = [{google_ad_client: "ca-pub-1234567890123456"}];</script>
        <a href="https://docs.partner.com/guide">Docs</a>
        <a href="https://blog.partner.com/post">Blog</a>
        <img src="https://cdn.assets.net/image.png" />
      </body>
    </html>
    """
    ads_txt = """
    google.com, pub-1234567890123456, DIRECT, f08c47fec0942fa0
    google.com, pub-1234567890123456, RESELLER, f08c47fec0942fa0
    """

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url in {"https://example.com", "https://example.com/"}:
            return httpx.Response(200, request=request, text=html)
        if url == "https://example.com/ads.txt":
            return httpx.Response(200, request=request, text=ads_txt)
        if url == "https://host.io/adsense/pub-1234567890123456":
            return httpx.Response(
                200,
                request=request,
                json={"domains": [{"domain": "example.com"}, {"domain": "othersite.com"}]},
            )
        if url == "https://worker.test/api/traffic/example.com":
            return httpx.Response(
                200,
                request=request,
                json={"monthly_visits": 1200, "month": "2026-03"},
            )
        if url == "https://worker.test/api/traffic/othersite.com":
            return httpx.Response(
                200,
                request=request,
                json={"data": {"monthlyVisits": 3400, "month": "2026-03"}},
            )
        if url == "https://worker.test/api/traffic/partner.com":
            return httpx.Response(
                200,
                request=request,
                json={"traffic": [{"month": "2026-02", "visits": 880}]},
            )
        if url == "https://worker.test/api/traffic/assets.net":
            return httpx.Response(
                200,
                request=request,
                json={"visits": 450},
            )
        if url in {
            "https://worker.test/api/whois?domain=othersite.com",
            "https://worker.test/api/whois?domain=partner.com",
            "https://worker.test/api/whois?domain=assets.net",
        }:
            return httpx.Response(
                200,
                request=request,
                json={"parsed": {"registrar": "Worker Registrar"}},
            )
        raise AssertionError(f"Unexpected URL {url}")

    service = build_service(handler)
    result = service.analyze(PubSpyAnalyzeRequest(url="example.com"))

    assert result.normalized_domain == "example.com"
    assert result.pub_id == "pub-1234567890123456"
    assert result.pub_id_display == "ca-pub-1234567890123456"
    assert result.pub_id_source == "html"
    assert result.ads_txt.has_google is True
    assert result.ads_txt.direct_count == 1
    assert result.ads_txt.reseller_count == 1
    assert result.current_domain.traffic.monthly_visits == 1200
    assert result.current_domain.whois.registrar == "Test Registrar"
    assert len(result.related_domains) == 1
    assert result.related_domains[0].domain == "othersite.com"
    assert result.related_domains[0].traffic.monthly_visits == 3400
    assert [item.domain for item in result.outbound_domains] == ["partner.com", "assets.net"]
    assert result.outbound_domains[0].count == 2
    assert result.outbound_domains[0].traffic.monthly_visits == 880


def test_pubspy_domain_metrics_falls_back_to_domain_search():
    seen_headers: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        seen_headers.append(request.headers.get("X-Client-Token"))
        if url == "https://worker.test/api/traffic/fallback.com":
            return httpx.Response(404, request=request, json={"message": "not found"})
        if url == "https://worker.test/api/domains?search=fallback.com&limit=50":
            return httpx.Response(
                200,
                request=request,
                json={"results": [{"domain": "fallback.com", "monthly_visits": 9999, "month": "2026-01"}]},
            )
        raise AssertionError(f"Unexpected URL {url}")

    service = build_service(handler)
    result = service.lookup_domain_metrics(PubSpyDomainMetricsRequest(domains=["fallback.com"]))

    assert result.domains[0].traffic.status == "success"
    assert result.domains[0].traffic.source == "domain_search"
    assert result.domains[0].traffic.monthly_visits == 9999
    assert seen_headers == ["token-123", "token-123"]


def test_pubspy_related_domains_can_skip_enrichment():
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == "https://host.io/adsense/pub-1234567890123456":
            return httpx.Response(
                200,
                request=request,
                json={"items": [{"domain": "alpha.com"}, {"domain": "beta.com"}]},
            )
        raise AssertionError(f"Unexpected URL {url}")

    service = build_service(handler)
    result = service.related_domains(
        PubSpyRelatedDomainsRequest(
            pub_id="pub-1234567890123456",
            current_domain="alpha.com",
            include_enrichment=False,
            max_domains=10,
        )
    )

    assert result.current_domain == "alpha.com"
    assert [item.domain for item in result.domains] == ["beta.com"]
    assert result.domains[0].traffic is None


def test_pubspy_related_domains_supports_hostio_html_pages():
    html = """
    <html><body>
      <ul class="text-sm flex flex-wrap">
        <li><a href="/alpha.com" rel="nofollow">alpha.com</a></li>
        <li><a href="/beta.com" rel="nofollow">beta.com</a></li>
        <li><a href="/alpha.com" rel="nofollow">alpha.com</a></li>
      </ul>
    </body></html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == "https://host.io/adsense/pub-1234567890123456":
            return httpx.Response(200, request=request, text=html, headers={"content-type": "text/html"})
        raise AssertionError(f"Unexpected URL {url}")

    service = build_service(handler)
    result = service.related_domains(
        PubSpyRelatedDomainsRequest(
            pub_id="pub-1234567890123456",
            current_domain="alpha.com",
            include_enrichment=False,
            max_domains=10,
        )
    )

    assert [item.domain for item in result.domains] == ["beta.com"]


def test_pubspy_domain_metrics_supports_month_keyed_traffic_maps():
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == "https://worker.test/api/traffic/mapped.com":
            return httpx.Response(
                200,
                request=request,
                json={
                    "error": 0,
                    "status": "cached",
                    "data": {
                        "domain": "mapped.com",
                        "traffic": {
                            "2026-01-01": 100,
                            "2026-02-01": 250,
                            "2026-03-01": 400,
                        },
                    },
                },
            )
        raise AssertionError(f"Unexpected URL {url}")

    service = build_service(handler)
    result = service.lookup_domain_metrics(PubSpyDomainMetricsRequest(domains=["mapped.com"]))

    assert result.domains[0].traffic.status == "success"
    assert result.domains[0].traffic.source == "traffic_api"
    assert result.domains[0].traffic.monthly_visits == 400
    assert result.domains[0].traffic.traffic_month == "2026-03-01"


def test_pubspy_domain_metrics_falls_back_to_worker_whois_when_local_lookup_is_empty():
    settings = AppSettings(
        pubspy_domain_query_base_url="https://worker.test",
        pubspy_hostio_base_url="https://host.io/adsense",
        pubspy_client_token="token-123",
        pubspy_http_timeout_seconds=5,
        pubspy_domain_query_timeout_seconds=5,
        pubspy_domain_search_limit=50,
        pubspy_cache_ttl_seconds=60,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == "https://worker.test/api/traffic/workerwhois.com":
            return httpx.Response(
                200,
                request=request,
                json={"monthly_visits": 222, "month": "2026-03"},
            )
        if url == "https://worker.test/api/whois?domain=workerwhois.com":
            return httpx.Response(
                200,
                request=request,
                json={
                    "parsed": {
                        "registrar": "NameCheap, Inc.",
                        "registered": "2025-07-09T16:25:58Z",
                        "expires": "2026-07-09T16:25:58Z",
                    }
                },
            )
        raise AssertionError(f"Unexpected URL {url}")

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    service = PubSpyService(settings=settings, whois_service=EmptyWhoisService(), client=client)

    result = service.lookup_domain_metrics(PubSpyDomainMetricsRequest(domains=["workerwhois.com"]))

    assert result.domains[0].traffic.monthly_visits == 222
    assert result.domains[0].whois.registrar == "NameCheap, Inc."
    assert result.domains[0].whois.created_date == "2025-07-09T16:25:58Z"
    assert result.domains[0].whois.expires_date == "2026-07-09T16:25:58Z"
