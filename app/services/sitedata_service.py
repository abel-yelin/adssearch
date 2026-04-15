from app.collectors.sitedata_browser_collector import SiteDataBrowserCollector
from app.collectors.sitedata_traffic_collector import SiteDataTrafficCollector
from app.core.config import get_settings
from app.schemas.sitedata import (
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
