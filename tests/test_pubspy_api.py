from app.dependencies.services import get_pubspy_service, get_sitedata_service
from app.schemas.pubspy import (
    PubSpyAdsTxtSummary,
    PubSpyAnalyzeResponse,
    PubSpyDomainMetric,
    PubSpyDomainMetricsResponse,
    PubSpyOutboundDomain,
    PubSpyRelatedDomainsResponse,
    PubSpyTrafficResult,
    PubSpyWhoisSummary,
)
from app.schemas.sitedata import SiteDataTrafficResponse


class FakePubSpyService:
    def analyze(self, request):
        return PubSpyAnalyzeResponse(
            input_url=request.url,
            page_url="https://example.com",
            normalized_domain="example.com",
            pub_id="pub-1234567890123456",
            pub_id_display="ca-pub-1234567890123456",
            pub_id_source="html",
            ads_txt=PubSpyAdsTxtSummary(
                url="https://example.com/ads.txt",
                found=True,
                has_google=True,
                matched_pub_id="pub-1234567890123456",
            ),
            current_domain=PubSpyDomainMetric(
                domain="example.com",
                is_current=True,
                traffic=PubSpyTrafficResult(
                    domain="example.com",
                    status="success",
                    formatted="1,200",
                    monthly_visits=1200,
                ),
                whois=PubSpyWhoisSummary(registrar="Test Registrar"),
                top_keywords=[],
            ),
            related_domains=[
                PubSpyDomainMetric(
                    domain="othersite.com",
                    traffic=PubSpyTrafficResult(
                        domain="othersite.com",
                        status="success",
                        formatted="3,400",
                        monthly_visits=3400,
                    ),
                )
            ],
            outbound_domains=[
                PubSpyOutboundDomain(
                    domain="partner.com",
                    count=2,
                    traffic=PubSpyTrafficResult(
                        domain="partner.com",
                        status="success",
                        formatted="880",
                        monthly_visits=880,
                    ),
                )
            ],
            warnings=[],
        )

    def related_domains(self, request):
        return PubSpyRelatedDomainsResponse(
            pub_id=request.pub_id,
            pub_id_display=f"ca-{request.pub_id}",
            current_domain=request.current_domain,
            domains=[PubSpyDomainMetric(domain="othersite.com")],
        )

    def lookup_domain_metrics(self, request):
        return PubSpyDomainMetricsResponse(
            domains=[
                PubSpyDomainMetric(
                    domain=request.domains[0],
                    traffic=PubSpyTrafficResult(
                        domain=request.domains[0],
                        status="success",
                        formatted="9,999",
                        monthly_visits=9999,
                    ),
                )
            ]
        )


class FakeSiteDataService:
    async def fetch_traffic(self, request):
        return SiteDataTrafficResponse(
            requested_domain=request.domain,
            resolved_domain=request.domain,
            collection_mode=request.collection_mode,
            site_name=request.domain,
            title="Example",
            description="Example domain",
            snapshot_date="2026-03-01T00:00:00+00:00",
            global_rank=10,
            category_rank=None,
            from_cache=True,
            monthly_visits=[],
            traffic_sources=[],
            top_keywords=[
                {"keyword": "image to url", "volume": 1200, "cpc": 0.2, "estimated_value": 500},
                {"keyword": "image url converter", "volume": 400, "cpc": 0.1, "estimated_value": 120},
            ],
            top_countries=[],
            engagements={},
        )


class FailingSiteDataService:
    async def fetch_traffic(self, request):
        raise RuntimeError("keyword source unavailable")


def test_pubspy_analyze_endpoint(client):
    from app.main import app

    app.dependency_overrides[get_pubspy_service] = lambda: FakePubSpyService()
    app.dependency_overrides[get_sitedata_service] = lambda: FakeSiteDataService()
    try:
        response = client.post("/api/pubspy/analyze", json={"url": "example.com"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["normalized_domain"] == "example.com"
    assert payload["pub_id"] == "pub-1234567890123456"
    assert payload["related_domains"][0]["domain"] == "othersite.com"


def test_pubspy_analyze_endpoint_can_include_top_keywords(client):
    from app.main import app

    app.dependency_overrides[get_pubspy_service] = lambda: FakePubSpyService()
    app.dependency_overrides[get_sitedata_service] = lambda: FakeSiteDataService()
    try:
        response = client.post(
            "/api/pubspy/analyze",
            json={"url": "example.com", "include_top_keywords": True},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["current_domain"]["top_keywords"][0]["keyword"] == "image to url"
    assert payload["current_domain"]["top_keywords"][0]["volume"] == 1200


def test_pubspy_analyze_endpoint_warns_when_top_keyword_enrichment_fails(client):
    from app.main import app

    app.dependency_overrides[get_pubspy_service] = lambda: FakePubSpyService()
    app.dependency_overrides[get_sitedata_service] = lambda: FailingSiteDataService()
    try:
        response = client.post(
            "/api/pubspy/analyze",
            json={"url": "example.com", "include_top_keywords": True},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["current_domain"]["top_keywords"] == []
    assert "Top keyword enrichment failed" in payload["warnings"][0]


def test_pubspy_related_domains_endpoint(client):
    from app.main import app

    app.dependency_overrides[get_pubspy_service] = lambda: FakePubSpyService()
    app.dependency_overrides[get_sitedata_service] = lambda: FakeSiteDataService()
    try:
        response = client.post(
            "/api/pubspy/related-domains",
            json={"pub_id": "pub-1234567890123456", "current_domain": "example.com"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["pub_id_display"] == "ca-pub-1234567890123456"
    assert payload["domains"][0]["domain"] == "othersite.com"


def test_pubspy_domain_metrics_endpoint(client):
    from app.main import app

    app.dependency_overrides[get_pubspy_service] = lambda: FakePubSpyService()
    app.dependency_overrides[get_sitedata_service] = lambda: FakeSiteDataService()
    try:
        response = client.post(
            "/api/pubspy/domain-metrics",
            json={"domains": ["fallback.com"]},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["domains"][0]["domain"] == "fallback.com"
    assert payload["domains"][0]["traffic"]["monthly_visits"] == 9999
