from typing import Any, Literal

from pydantic import BaseModel, Field


class SiteDataTrafficRequest(BaseModel):
    domain: str = Field(..., min_length=1, description="Domain to analyze on SiteData.")
    collection_mode: Literal["direct", "browser"] = Field(
        default="browser",
        description="Use direct API signing or a real browser session.",
    )
    sync_cf_token_from_browser: bool = Field(
        default=False,
        description="For direct mode, load cf_token and anonClientId from a configured browser session first.",
    )
    client_id: str | None = Field(default=None, description="Optional explicit SiteData clientId override.")
    cf_token: str | None = Field(default=None, description="Optional explicit SiteData cf_token override.")
    proxy: str | None = Field(default=None, description="Optional proxy passed to curl.")
    timeout_seconds: int = Field(default=30, ge=5, le=120, description="Request timeout in seconds.")
    browser_mode: Literal["isolated", "cdp", "persistent"] | None = Field(
        default=None,
        description="Browser collector mode.",
    )
    browser_cdp_url: str | None = Field(default=None, description="Chrome DevTools endpoint for CDP mode.")
    browser_executable_path: str | None = Field(default=None, description="Browser executable path.")
    browser_user_data_dir: str | None = Field(default=None, description="User data dir for persistent mode.")
    browser_channel: str | None = Field(default=None, description="Browser channel such as chrome.")
    browser_extension_path: str | None = Field(default=None, description="Optional browser extension path.")
    browser_headless: bool = Field(default=True, description="Whether the browser collector should run headless.")
    browser_timeout_ms: int = Field(default=30000, ge=5000, le=180000, description="Browser timeout in milliseconds.")
    browser_pre_click_wait_ms: int = Field(
        default=3000,
        ge=0,
        le=60000,
        description="Wait before clicking Analyze.",
    )
    browser_post_click_wait_ms: int = Field(
        default=8000,
        ge=0,
        le=60000,
        description="Wait after clicking Analyze.",
    )


class SiteDataBrowserHealthRequest(BaseModel):
    probe_domain: str = Field(default="verifieddr.com", min_length=1, description="Domain used for a lightweight probe.")
    browser_mode: Literal["isolated", "cdp", "persistent"] | None = Field(
        default=None,
        description="Browser collector mode.",
    )
    browser_cdp_url: str | None = Field(default=None, description="Chrome DevTools endpoint for CDP mode.")
    browser_executable_path: str | None = Field(default=None, description="Browser executable path.")
    browser_user_data_dir: str | None = Field(default=None, description="User data dir for persistent mode.")
    browser_channel: str | None = Field(default=None, description="Browser channel such as chrome.")
    browser_extension_path: str | None = Field(default=None, description="Optional browser extension path.")
    browser_headless: bool = Field(default=True, description="Whether the browser collector should run headless.")
    browser_timeout_ms: int = Field(default=30000, ge=5000, le=180000, description="Browser timeout in milliseconds.")
    browser_pre_click_wait_ms: int = Field(
        default=3000,
        ge=0,
        le=60000,
        description="Wait before clicking Analyze.",
    )
    browser_post_click_wait_ms: int = Field(
        default=8000,
        ge=0,
        le=60000,
        description="Wait after clicking Analyze.",
    )


class SiteDataTrafficMonthlyVisit(BaseModel):
    month: str
    visits: int


class SiteDataTrafficSource(BaseModel):
    source: str
    share_percent: float


class SiteDataTrafficKeyword(BaseModel):
    keyword: str
    volume: int | None = None
    cpc: float | None = None
    estimated_value: int | None = None


class SiteDataTrafficCountry(BaseModel):
    country_code: str
    share_percent: float


class SiteDataTrafficResponse(BaseModel):
    requested_domain: str
    resolved_domain: str
    collection_mode: str = "direct"
    site_name: str | None = None
    title: str | None = None
    description: str | None = None
    snapshot_date: str | None = None
    global_rank: int | None = None
    category_rank: int | None = None
    from_cache: bool = False
    monthly_visits: list[SiteDataTrafficMonthlyVisit]
    traffic_sources: list[SiteDataTrafficSource]
    top_keywords: list[SiteDataTrafficKeyword]
    top_countries: list[SiteDataTrafficCountry]
    engagements: dict[str, Any]
    browser_debug: dict[str, Any] | None = None


class SiteDataBrowserHealthResponse(BaseModel):
    probe_domain: str
    browser_mode: str
    current_url: str | None = None
    has_user_info: bool = False
    has_cf_token: bool = False
    has_anon_client_id: bool = False
    last_browser_collection_usable: bool = False
    requires_manual_login: bool = False
    status: Literal["healthy", "needs_manual_login", "browser_error"] = "browser_error"
    failure_code: str | None = None
    message: str
    recommended_action: str
    manual_login_url: str | None = None
    manual_login_steps: list[str] = Field(default_factory=list)
    request_count: int = 0
    recent_console: list[str] = Field(default_factory=list)
