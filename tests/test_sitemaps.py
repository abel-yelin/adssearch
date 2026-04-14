import gzip

import httpx

from app.dependencies.services import get_sitemap_service
from app.schemas.sitemap import (
    SitemapMonitorCreateResponse,
    SitemapMonitorListResponse,
    SitemapMonitorResponse,
    SitemapRecentUrlsResponse,
    SitemapRunDispatchResponse,
    SitemapRunResponse,
)
from app.services.sitemap_fetcher import SitemapFetcher


class FakeSitemapService:
    def create_monitor(self, request):
        return SitemapMonitorCreateResponse(
            monitor_id="monitor-123",
            status="idle",
            sitemap_url="https://example.com/sitemap.xml",
            next_check_at=None,
        )

    def list_monitors(self):
        return SitemapMonitorListResponse(
            items=[
                SitemapMonitorResponse(
                    monitor_id="monitor-123",
                    site_url="https://example.com",
                    sitemap_url="https://example.com/sitemap.xml",
                    interval_minutes=5,
                    enabled=True,
                    status="completed",
                    latest_run_id="run-123",
                    latest_result={"summary": {"new_url_count": 1}},
                )
            ]
        )

    def get_monitor(self, monitor_id):
        return SitemapMonitorResponse(
            monitor_id=monitor_id,
            site_url="https://example.com",
            sitemap_url="https://example.com/sitemap.xml",
            interval_minutes=5,
            enabled=True,
            status="completed",
            latest_run_id="run-123",
            latest_result={"summary": {"new_url_count": 1}},
        )

    def dispatch_run(self, monitor_id, trigger_mode="manual"):
        return SitemapRunDispatchResponse(
            monitor_id=monitor_id,
            run_id="run-123",
            status="pending",
            trigger_mode=trigger_mode,
            message="Sitemap monitor task queued successfully.",
        )

    def get_run(self, run_id):
        return SitemapRunResponse(
            run_id=run_id,
            monitor_id="monitor-123",
            trigger_mode="manual",
            status="completed",
            result={"summary": {"new_url_count": 1}},
            created_at="2026-04-15T00:00:00Z",
            updated_at="2026-04-15T00:00:00Z",
            started_at="2026-04-15T00:00:00Z",
            finished_at="2026-04-15T00:01:00Z",
        )

    def get_recent_new_urls(self, monitor_id):
        return SitemapRecentUrlsResponse(
            monitor_id=monitor_id,
            site_url="https://example.com",
            sitemap_url="https://example.com/sitemap.xml",
            latest_new_urls=[
                {
                    "url": "https://example.com/new-post",
                    "lastmod": "2026-04-15T00:00:00+00:00",
                    "source_sitemap": "https://example.com/post-sitemap.xml",
                }
            ],
            summary={"new_url_count": 1},
        )


def test_create_sitemap_monitor_endpoint(client):
    from app.main import app

    app.dependency_overrides[get_sitemap_service] = lambda: FakeSitemapService()
    try:
        response = client.post(
            "/api/sitemaps/monitors",
            json={
                "site_url": "https://example.com",
                "interval_minutes": 5,
                "enabled": True,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    payload = response.json()
    assert payload["monitor_id"] == "monitor-123"
    assert payload["sitemap_url"] == "https://example.com/sitemap.xml"


def test_list_sitemap_monitors_endpoint(client):
    from app.main import app

    app.dependency_overrides[get_sitemap_service] = lambda: FakeSitemapService()
    try:
        response = client.get("/api/sitemaps/monitors")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 1
    assert payload["items"][0]["monitor_id"] == "monitor-123"


def test_run_sitemap_monitor_endpoint(client):
    from app.main import app

    app.dependency_overrides[get_sitemap_service] = lambda: FakeSitemapService()
    try:
        response = client.post("/api/sitemaps/monitors/monitor-123/run")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    payload = response.json()
    assert payload["run_id"] == "run-123"
    assert payload["trigger_mode"] == "manual"


def test_recent_new_urls_endpoint(client):
    from app.main import app

    app.dependency_overrides[get_sitemap_service] = lambda: FakeSitemapService()
    try:
        response = client.get("/api/sitemaps/monitors/monitor-123/recent-new-urls")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["new_url_count"] == 1
    assert payload["latest_new_urls"][0]["url"] == "https://example.com/new-post"


def test_fetcher_supports_index_gzip_and_conditional_requests():
    root_url = "https://example.com/sitemap_index.xml"
    child_url = "https://example.com/post-sitemap.xml.gz"
    root_xml = f"""
    <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <sitemap><loc>{child_url}</loc><lastmod>2026-04-14T00:00:00+00:00</lastmod></sitemap>
    </sitemapindex>
    """.strip().encode()
    child_xml = """
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://example.com/a</loc><lastmod>2026-04-14</lastmod></url>
      <url><loc>https://example.com/b</loc><lastmod>2026-04-15</lastmod></url>
    </urlset>
    """.strip().encode()
    child_gzip = gzip.compress(child_xml)

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == root_url:
            if request.headers.get("if-none-match") == '"root-v1"':
                return httpx.Response(304, request=request)
            return httpx.Response(
                200,
                request=request,
                headers={"etag": '"root-v1"', "content-type": "application/xml"},
                content=root_xml,
            )
        if str(request.url) == child_url:
            if request.headers.get("if-none-match") == '"child-v1"':
                return httpx.Response(304, request=request)
            return httpx.Response(
                200,
                request=request,
                headers={"etag": '"child-v1"', "content-type": "application/gzip"},
                content=child_gzip,
            )
        raise AssertionError(f"Unexpected URL {request.url}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetcher = SitemapFetcher(client=client)

    snapshot1, stats1 = fetcher.fetch_snapshot(root_url)
    snapshot2, stats2 = fetcher.fetch_snapshot(root_url, snapshot1)

    assert stats1["file_count"] == 2
    assert stats1["url_count"] == 2
    assert snapshot1["url_entries"]["https://example.com/b"]["lastmod"] == "2026-04-15"
    assert snapshot2["files"][root_url]["etag"] == '"root-v1"'
    assert stats2["reused_files"] == 2
    assert stats2["downloaded_files"] == 0
