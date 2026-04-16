import asyncio
import subprocess
import re
from unittest.mock import AsyncMock, Mock, patch

from playwright._impl._errors import Error as PlaywrightError

from app.collectors.sitedata_traffic_collector import SiteDataTrafficCollector, SiteDataTrafficCollectorError
from app.collectors.sitedata_browser_collector import SiteDataBrowserCollector
from app.dependencies.services import get_sitedata_service
from app.schemas.sitedata import SiteDataBrowserHealthResponse, SiteDataTrafficRequest, SiteDataTrafficResponse
from app.services.sitedata_service import SiteDataTrafficService


def test_sitedata_collector_parses_successful_response():
    collector = SiteDataTrafficCollector()
    body = (
        '{"SiteName":"chatgpt.com","SnapshotDate":"2026-03-01T00:00:00+00:00",'
        '"EstimatedMonthlyVisits":{"2026-01-01":10,"2026-02-01":20},'
        '"TrafficSources":{"Direct":0.5,"Search":0.3},'
        '"TopKeywords":[{"Name":"chatgpt","Volume":100,"Cpc":0.1,"EstimatedValue":200}],'
        '"TopCountryShares":[{"CountryCode":"US","Value":0.4}],'
        '"Engagments":{"Visits":"20"},"fromCache":true}\n__STATUS__:200'
    )

    with patch("app.collectors.sitedata_traffic_collector.subprocess.run") as run:
        run.return_value = subprocess.CompletedProcess(args=["curl"], returncode=0, stdout=body, stderr="")
        payload = collector.fetch("chatgpt.com")

    assert payload["SiteName"] == "chatgpt.com"
    assert payload["resolved_domain"] == "chatgpt.com"
    assert payload["EstimatedMonthlyVisits"]["2026-02-01"] == 20


def test_sitedata_collector_retries_without_www_on_unauthorized():
    collector = SiteDataTrafficCollector()
    outputs = [
        subprocess.CompletedProcess(
            args=["curl"],
            returncode=0,
            stdout='{"error":"Unauthorized clientId"}\n__STATUS__:429',
            stderr="",
        ),
        subprocess.CompletedProcess(
            args=["curl"],
            returncode=0,
            stdout='{"SiteName":"image2url.com","EstimatedMonthlyVisits":{},"TrafficSources":{},"TopKeywords":[],"TopCountryShares":[],"Engagments":{}}\n__STATUS__:200',
            stderr="",
        ),
    ]

    with patch("app.collectors.sitedata_traffic_collector.subprocess.run", side_effect=outputs):
        payload = collector.fetch("www.image2url.com")

    assert payload["requested_domain"] == "www.image2url.com"
    assert payload["resolved_domain"] == "image2url.com"


def test_sitedata_collector_raises_for_invalid_domain():
    collector = SiteDataTrafficCollector()
    try:
        collector.fetch("not-a-domain")
    except SiteDataTrafficCollectorError as exc:
        assert exc.code == "invalid_domain"
    else:
        raise AssertionError("Expected invalid_domain error")


def test_sitedata_collector_generates_browser_compatible_client_id():
    client_id = SiteDataTrafficCollector._generate_client_id()

    assert re.fullmatch(r"anon_\d{13}_[a-z0-9]{13}", client_id)


def test_sitedata_collector_reuses_cached_client_id_within_process():
    SiteDataTrafficCollector._anon_client_id_cache = None
    try:
        first = SiteDataTrafficCollector._get_or_create_client_id()
        second = SiteDataTrafficCollector._get_or_create_client_id()
    finally:
        SiteDataTrafficCollector._anon_client_id_cache = None

    assert first == second


def test_sitedata_collector_build_signed_params_supports_explicit_client_and_cf_token():
    collector = SiteDataTrafficCollector()
    params = collector._build_signed_params(
        "image2url.com",
        client_id="anon_1776359491454_7618266557315",
        cf_token="cf-demo-token",
    )

    assert params["clientId"] == "anon_1776359491454_7618266557315"
    assert params["cf_token"] == "cf-demo-token"
    assert params["domain"] == "image2url.com"
    assert len(params["sign"]) == 32


class FakeSiteDataService:
    async def fetch_traffic(self, request):
        return SiteDataTrafficResponse(
            requested_domain=request.domain,
            resolved_domain=request.domain,
            collection_mode="direct",
            site_name=request.domain,
            title="Example",
            description="Example domain",
            snapshot_date="2026-03-01T00:00:00+00:00",
            global_rank=10,
            category_rank=None,
            from_cache=True,
            monthly_visits=[
                {"month": "2026-01-01", "visits": 10},
                {"month": "2026-02-01", "visits": 20},
            ],
            traffic_sources=[
                {"source": "Direct", "share_percent": 50.0},
            ],
            top_keywords=[
                {"keyword": "example", "volume": 100, "cpc": 0.1, "estimated_value": 200},
            ],
            top_countries=[
                {"country_code": "US", "share_percent": 40.0},
            ],
            engagements={"Visits": "20"},
        )

    async def check_browser_health(self, request):
        return SiteDataBrowserHealthResponse(
            probe_domain=request.probe_domain,
            browser_mode="cdp",
            current_url="https://sitedata.dev/traffic/verifieddr.com",
            has_user_info=True,
            has_cf_token=True,
            has_anon_client_id=True,
            last_browser_collection_usable=True,
            requires_manual_login=False,
            status="healthy",
            failure_code=None,
            message="Browser session is healthy and SiteData collection is currently usable.",
            recommended_action="No action needed.",
            manual_login_url="http://192.168.0.4:6080/vnc.html",
            manual_login_steps=["Open the VNC browser session at the provided URL."],
            request_count=1,
            recent_console=[],
        )


def test_sitedata_service_supports_browser_collector():
    payload = {
        "requested_domain": "www.image2url.com",
        "resolved_domain": "image2url.com",
        "SiteName": "image2url.com",
        "EstimatedMonthlyVisits": {"2026-01-01": 217000, "2026-03-01": 679000},
        "TrafficSources": {"Search": 0.534, "Direct": 0.333},
        "TopKeywords": [{"Name": "image to url", "Volume": 1000, "Cpc": 0.2, "EstimatedValue": 500}],
        "TopCountryShares": [{"CountryCode": "US", "Value": 0.309}],
        "Engagments": {"MonthlyVisits": "679K"},
        "browser_debug": {"request_count": 2},
    }

    with patch("app.services.sitedata_service.SiteDataBrowserCollector") as collector_cls:
        collector = collector_cls.return_value
        collector.start = AsyncMock()
        collector.fetch = AsyncMock(return_value=payload)
        collector.close = AsyncMock()
        response = asyncio.run(
            SiteDataTrafficService().fetch_traffic(
                SiteDataTrafficRequest(
                    domain="www.image2url.com",
                    collection_mode="browser",
                    browser_mode="cdp",
                    browser_cdp_url="http://127.0.0.1:9222",
                )
            )
        )

    collector.start.assert_awaited_once()
    collector.fetch.assert_awaited_once()
    collector.close.assert_awaited_once()
    assert response.collection_mode == "browser"
    assert response.resolved_domain == "image2url.com"
    assert response.browser_debug == {"request_count": 2}
    assert response.monthly_visits[-1].visits == 679000


def test_sitedata_service_can_sync_browser_tokens_for_direct_mode():
    payload = {
        "requested_domain": "image2url.com",
        "resolved_domain": "image2url.com",
        "SiteName": "image2url.com",
        "EstimatedMonthlyVisits": {"2026-03-01": 679000},
        "TrafficSources": {"Search": 0.534},
        "TopKeywords": [{"Name": "image to url", "Volume": 1000, "Cpc": 0.2, "EstimatedValue": 500}],
        "TopCountryShares": [{"CountryCode": "US", "Value": 0.309}],
        "Engagments": {"Visits": "679000"},
    }

    with patch("app.services.sitedata_service.SiteDataBrowserCollector") as browser_cls, patch(
        "app.services.sitedata_service.SiteDataTrafficCollector"
    ) as direct_cls:
        browser = browser_cls.return_value
        browser.start = AsyncMock()
        browser.read_session_tokens = AsyncMock(
            return_value={
                "probe_domain": "image2url.com",
                "anon_client_id": "anon_1776359491454_7618266557315",
                "cf_token": "cf-demo-token",
            }
        )
        browser.close = AsyncMock()

        direct = direct_cls.return_value
        direct.fetch.return_value = payload

        response = asyncio.run(
            SiteDataTrafficService().fetch_traffic(
                SiteDataTrafficRequest(
                    domain="image2url.com",
                    collection_mode="direct",
                    sync_cf_token_from_browser=True,
                    browser_mode="cdp",
                    browser_cdp_url="http://127.0.0.1:9222",
                )
            )
        )

    browser.start.assert_awaited_once()
    browser.read_session_tokens.assert_awaited_once()
    browser.close.assert_awaited_once()
    direct.fetch.assert_called_once_with(
        "image2url.com",
        client_id="anon_1776359491454_7618266557315",
        cf_token="cf-demo-token",
    )
    assert response.resolved_domain == "image2url.com"
    assert response.top_keywords[0].keyword == "image to url"


def test_sitedata_service_sync_mode_raises_verification_required_when_token_missing():
    with patch("app.services.sitedata_service.SiteDataBrowserCollector") as browser_cls, patch(
        "app.services.sitedata_service.SiteDataTrafficCollector"
    ) as direct_cls:
        browser = browser_cls.return_value
        browser.start = AsyncMock()
        browser.read_session_tokens = AsyncMock(
            return_value={
                "probe_domain": "image2url.com",
                "anon_client_id": "anon_1776359491454_7618266557315",
                "cf_token": None,
                "has_cf_token": False,
            }
        )
        browser.close = AsyncMock()

        direct = direct_cls.return_value
        direct.fetch.side_effect = SiteDataTrafficCollectorError("unauthorized_client", "Unauthorized clientId")

        try:
            asyncio.run(
                SiteDataTrafficService().fetch_traffic(
                    SiteDataTrafficRequest(
                        domain="image2url.com",
                        collection_mode="direct",
                        sync_cf_token_from_browser=True,
                        browser_mode="cdp",
                        browser_cdp_url="http://127.0.0.1:9222",
                    )
                )
            )
        except SiteDataTrafficCollectorError as exc:
            assert exc.code == "verification_required"
            assert "cf_token" in exc.message
        else:
            raise AssertionError("Expected verification_required when sync mode has no usable cf_token")


def test_sitedata_traffic_endpoint(client):
    from app.main import app

    app.dependency_overrides[get_sitedata_service] = lambda: FakeSiteDataService()
    try:
        response = client.post(
            "/api/sitedata/traffic",
            json={"domain": "chatgpt.com"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["requested_domain"] == "chatgpt.com"
    assert payload["monthly_visits"][1]["visits"] == 20


def test_sitedata_browser_health_endpoint(client):
    from app.main import app

    app.dependency_overrides[get_sitedata_service] = lambda: FakeSiteDataService()
    try:
        response = client.post(
            "/api/sitedata/browser-health",
            json={"probe_domain": "verifieddr.com"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["probe_domain"] == "verifieddr.com"
    assert payload["has_user_info"] is True
    assert payload["requires_manual_login"] is False


def test_sitedata_service_browser_health_supports_verified_session():
    health_payload = {
        "probe_domain": "verifieddr.com",
        "current_url": "https://sitedata.dev/traffic/verifieddr.com",
        "has_user_info": True,
        "has_cf_token": True,
        "has_anon_client_id": True,
        "last_browser_collection_usable": True,
        "requires_manual_login": False,
        "failure_code": None,
        "request_count": 1,
        "recent_console": ["✅ Fetch completed. Data exists: true Error: none"],
    }

    with patch("app.services.sitedata_service.SiteDataBrowserCollector") as collector_cls:
        collector = collector_cls.return_value
        collector.start = AsyncMock()
        collector.check_health = AsyncMock(return_value=health_payload)
        collector.close = AsyncMock()
        response = asyncio.run(
            SiteDataTrafficService().check_browser_health(
                request=type(
                    "Req",
                    (),
                    {
                        "probe_domain": "verifieddr.com",
                        "browser_headless": True,
                        "browser_timeout_ms": 30000,
                        "browser_mode": "cdp",
                        "browser_cdp_url": "http://127.0.0.1:9222",
                        "browser_executable_path": None,
                        "browser_user_data_dir": None,
                        "browser_channel": None,
                        "browser_extension_path": None,
                        "browser_pre_click_wait_ms": 3000,
                        "browser_post_click_wait_ms": 8000,
                    },
                )()
            )
        )

    assert response.status == "healthy"
    assert response.last_browser_collection_usable is True
    assert response.requires_manual_login is False


def test_sitedata_browser_collector_check_health_tolerates_err_aborted():
    collector = SiteDataBrowserCollector(browser_mode="cdp", browser_cdp_url="http://127.0.0.1:9222")
    collector._page = Mock()
    collector._page.goto = AsyncMock(
        side_effect=PlaywrightError(
        'Page.goto: net::ERR_ABORTED at https://sitedata.dev/traffic/image2url.com'
        )
    )
    collector._page.wait_for_timeout = AsyncMock()
    analyze_button = AsyncMock()
    analyze_button.click = AsyncMock()
    collector._page.get_by_role.return_value = analyze_button
    collector._read_storage = AsyncMock(
        side_effect=[
            {
                "href": "https://sitedata.dev/traffic/image2url.com",
                "localKeys": ["anonClientId", "userInfo", "cf_token"],
                "userInfo": '{"email":"test@example.com"}',
                "anonClientId": "anon_demo",
                "cfToken": "cf_demo",
            },
            {
                "href": "https://sitedata.dev/traffic/image2url.com",
                "localKeys": ["anonClientId", "userInfo", "cf_token"],
                "userInfo": '{"email":"test@example.com"}',
                "anonClientId": "anon_demo",
                "cfToken": "cf_demo",
            },
        ]
    )
    collector._extract_latest_payload = lambda: {"SiteName": "image2url.com"}

    payload = asyncio.run(collector.check_health("image2url.com"))

    assert payload["has_cf_token"] is True
    assert payload["last_browser_collection_usable"] is True
    collector._page.get_by_role.assert_called_once_with("button", name="Analyze")
