from app.collectors.sitedata_browser_collector import SiteDataBrowserCollector
from app.collectors.sitedata_traffic_collector import SiteDataTrafficCollector
from app.core.config import get_settings
from app.schemas.sitedata import (
    SiteDataBrowserHealthRequest,
    SiteDataBrowserHealthResponse,
    SiteDataTrafficCountry,
    SiteDataTrafficKeyword,
    SiteDataTrafficMonthlyVisit,
    SiteDataTrafficRequest,
    SiteDataTrafficResponse,
    SiteDataTrafficSource,
)


class SiteDataTrafficService:
    def __init__(self):
        self.settings = get_settings()

    async def fetch_traffic(self, request: SiteDataTrafficRequest) -> SiteDataTrafficResponse:
        if request.collection_mode == "browser":
            collector = SiteDataBrowserCollector(
                headless=request.browser_headless,
                timeout_ms=request.browser_timeout_ms,
                browser_mode=request.browser_mode or self.settings.trend_browser_mode,
                browser_cdp_url=request.browser_cdp_url or self.settings.trend_browser_cdp_url,
                browser_executable_path=request.browser_executable_path or self.settings.trend_browser_executable_path,
                browser_user_data_dir=request.browser_user_data_dir or self.settings.trend_browser_user_data_dir,
                browser_channel=request.browser_channel or self.settings.trend_browser_channel,
                browser_extension_path=request.browser_extension_path or self.settings.trend_browser_extension_path,
            )
            await collector.start()
            try:
                payload = await collector.fetch(
                    request.domain,
                    pre_click_wait_ms=request.browser_pre_click_wait_ms,
                    post_click_wait_ms=request.browser_post_click_wait_ms,
                )
            finally:
                await collector.close()
        else:
            collector = SiteDataTrafficCollector(
                timeout_seconds=request.timeout_seconds,
                proxy=request.proxy,
            )
            payload = collector.fetch(request.domain)

        return self._build_response(payload, request.collection_mode)

    async def check_browser_health(self, request: SiteDataBrowserHealthRequest) -> SiteDataBrowserHealthResponse:
        collector = SiteDataBrowserCollector(
            headless=request.browser_headless,
            timeout_ms=request.browser_timeout_ms,
            browser_mode=request.browser_mode or self.settings.trend_browser_mode,
            browser_cdp_url=request.browser_cdp_url or self.settings.trend_browser_cdp_url,
            browser_executable_path=request.browser_executable_path or self.settings.trend_browser_executable_path,
            browser_user_data_dir=request.browser_user_data_dir or self.settings.trend_browser_user_data_dir,
            browser_channel=request.browser_channel or self.settings.trend_browser_channel,
            browser_extension_path=request.browser_extension_path or self.settings.trend_browser_extension_path,
        )
        try:
            await collector.start()
            payload = await collector.check_health(
                request.probe_domain or self.settings.sitedata_health_probe_domain,
                pre_click_wait_ms=request.browser_pre_click_wait_ms,
                post_click_wait_ms=request.browser_post_click_wait_ms,
            )
            return self._build_browser_health_response(
                payload,
                browser_mode=request.browser_mode or self.settings.trend_browser_mode,
            )
        except SiteDataTrafficCollectorError as exc:
            return self._build_browser_health_error_response(
                request=request,
                browser_mode=request.browser_mode or self.settings.trend_browser_mode,
                code=exc.code,
                message=exc.message,
            )
        finally:
            try:
                await collector.close()
            except Exception:
                pass

    def _build_response(self, payload: dict, collection_mode: str) -> SiteDataTrafficResponse:
        visits = [
            SiteDataTrafficMonthlyVisit(month=month, visits=int(value))
            for month, value in sorted((payload.get("EstimatedMonthlyVisits") or {}).items())
        ]
        traffic_sources = [
            SiteDataTrafficSource(source=source, share_percent=round(float(value) * 100, 2))
            for source, value in sorted((payload.get("TrafficSources") or {}).items(), key=lambda item: item[1], reverse=True)
        ]
        top_keywords = [
            SiteDataTrafficKeyword(
                keyword=item.get("Name") or "",
                volume=item.get("Volume"),
                cpc=item.get("Cpc"),
                estimated_value=item.get("EstimatedValue"),
            )
            for item in (payload.get("TopKeywords") or [])
            if item.get("Name")
        ]
        top_countries = [
            SiteDataTrafficCountry(
                country_code=item.get("CountryCode") or "",
                share_percent=round(float(item.get("Value") or 0) * 100, 2),
            )
            for item in (payload.get("TopCountryShares") or [])
            if item.get("CountryCode")
        ]

        return SiteDataTrafficResponse(
            requested_domain=payload.get("requested_domain") or "",
            resolved_domain=payload.get("resolved_domain") or "",
            collection_mode=collection_mode,
            site_name=payload.get("SiteName"),
            title=payload.get("Title"),
            description=payload.get("Description"),
            snapshot_date=payload.get("SnapshotDate"),
            global_rank=(payload.get("GlobalRank") or {}).get("Rank"),
            category_rank=self._read_category_rank(payload.get("CategoryRank")),
            from_cache=bool(payload.get("fromCache")),
            monthly_visits=visits,
            traffic_sources=traffic_sources,
            top_keywords=top_keywords,
            top_countries=top_countries,
            engagements=payload.get("Engagments") or {},
            browser_debug=payload.get("browser_debug"),
        )

    def _build_browser_health_response(self, payload: dict, *, browser_mode: str) -> SiteDataBrowserHealthResponse:
        healthy = bool(payload.get("last_browser_collection_usable"))
        requires_manual_login = bool(payload.get("requires_manual_login"))
        if healthy:
            status = "healthy"
            message = "Browser session is healthy and SiteData collection is currently usable."
            recommended_action = "No action needed. You can continue using the browser collector."
        elif requires_manual_login:
            status = "needs_manual_login"
            message = "Browser session is missing the state required by SiteData. Manual login or verification is needed."
            recommended_action = "Open the VNC browser session, sign in if needed, pass any Cloudflare verification, then retry."
        else:
            status = "browser_error"
            message = "Browser session is not currently usable for SiteData, but this does not look like a login-state issue."
            recommended_action = "Check that the Chrome debug session is running and that the browser configuration still matches the collector."

        return SiteDataBrowserHealthResponse(
            probe_domain=payload.get("probe_domain") or self.settings.sitedata_health_probe_domain,
            browser_mode=browser_mode,
            current_url=payload.get("current_url"),
            has_user_info=bool(payload.get("has_user_info")),
            has_cf_token=bool(payload.get("has_cf_token")),
            has_anon_client_id=bool(payload.get("has_anon_client_id")),
            last_browser_collection_usable=healthy,
            requires_manual_login=requires_manual_login,
            status=status,
            failure_code=payload.get("failure_code"),
            message=message,
            recommended_action=recommended_action,
            manual_login_url=self.settings.browser_manual_login_url,
            manual_login_steps=self._manual_login_steps(),
            request_count=int(payload.get("request_count") or 0),
            recent_console=list(payload.get("recent_console") or []),
        )

    def _build_browser_health_error_response(
        self,
        *,
        request: SiteDataBrowserHealthRequest,
        browser_mode: str,
        code: str,
        message: str,
    ) -> SiteDataBrowserHealthResponse:
        requires_manual_login = code == "verification_required"
        status = "needs_manual_login" if requires_manual_login else "browser_error"
        recommended_action = (
            "Open the VNC browser session, complete Google or Cloudflare verification, then retry the health check."
            if requires_manual_login
            else "Check that the Chrome debug session is running and that the configured browser mode and CDP URL are correct."
        )
        return SiteDataBrowserHealthResponse(
            probe_domain=request.probe_domain or self.settings.sitedata_health_probe_domain,
            browser_mode=browser_mode,
            status=status,
            has_user_info=False,
            has_cf_token=False,
            has_anon_client_id=False,
            last_browser_collection_usable=False,
            requires_manual_login=requires_manual_login,
            failure_code=code,
            message=message,
            recommended_action=recommended_action,
            manual_login_url=self.settings.browser_manual_login_url,
            manual_login_steps=self._manual_login_steps(),
            request_count=0,
            recent_console=[],
        )

    @staticmethod
    def _read_category_rank(payload: dict | None) -> int | None:
        if not payload:
            return None
        raw = payload.get("Rank")
        if raw in {None, "", "0", 0}:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _manual_login_steps() -> list[str]:
        return [
            "Open the VNC browser session at the provided URL.",
            "If SiteData or Google asks you to sign in, complete the login in that browser window.",
            "If Cloudflare or another verification page appears, finish the manual verification there.",
            "Keep the same Chrome profile and browser window open, then rerun the health check or collection request.",
        ]
