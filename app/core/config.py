import os
from functools import lru_cache

from pydantic import BaseModel, Field


def _get_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_list_env(name: str, default: list[str]) -> list[str]:
    value = os.getenv(name)
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


def _get_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


class AppSettings(BaseModel):
    app_name: str = Field(default="adssearch")
    app_env: str = Field(default=os.getenv("APP_ENV", "development"))
    debug: bool = Field(default_factory=lambda: _get_bool_env("APP_DEBUG", False))
    title: str = Field(default="Google Ads Transparency Scraper API")
    description: str = Field(default="查询域名在 Google Ads Transparency Center 的广告主和关联域名")
    version: str = Field(default=os.getenv("APP_VERSION", "1.0.0"))
    api_prefix: str = Field(default=os.getenv("API_PREFIX", "/api"))
    docs_url: str | None = Field(default="/docs")
    redoc_url: str | None = Field(default="/redoc")
    openapi_url: str | None = Field(default="/openapi.json")
    allow_origins: list[str] = Field(default_factory=lambda: _get_list_env("ALLOW_ORIGINS", ["*"]))
    allow_credentials: bool = Field(default_factory=lambda: _get_bool_env("ALLOW_CREDENTIALS", True))
    allow_methods: list[str] = Field(default_factory=lambda: _get_list_env("ALLOW_METHODS", ["*"]))
    allow_headers: list[str] = Field(default_factory=lambda: _get_list_env("ALLOW_HEADERS", ["*"]))
    log_level: str = Field(default=os.getenv("LOG_LEVEL", "INFO").upper())
    default_region: str = Field(default=os.getenv("DEFAULT_REGION", "anywhere"))
    default_timeout_ms: int = Field(default_factory=lambda: _get_int_env("DEFAULT_TIMEOUT_MS", 30000))
    default_max_scroll_pages: int = Field(default_factory=lambda: _get_int_env("DEFAULT_MAX_SCROLL_PAGES", 10))
    redis_url: str = Field(default=os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    queue_name: str = Field(default=os.getenv("QUEUE_NAME", "adssearch"))
    queue_job_timeout: int = Field(default_factory=lambda: _get_int_env("QUEUE_JOB_TIMEOUT", 1800))
    queue_result_ttl: int = Field(default_factory=lambda: _get_int_env("QUEUE_RESULT_TTL", 86400))
    queue_failure_ttl: int = Field(default_factory=lambda: _get_int_env("QUEUE_FAILURE_TTL", 86400))
    queue_default_retry_count: int = Field(default_factory=lambda: _get_int_env("QUEUE_DEFAULT_RETRY_COUNT", 1))
    database_url: str = Field(default=os.getenv("DATABASE_URL", "sqlite:///./adssearch.db"))
    trend_default_proxy: str | None = Field(
        default=os.getenv("TRENDS_PROXY")
        or os.getenv("ALL_PROXY")
        or os.getenv("all_proxy")
        or os.getenv("HTTPS_PROXY")
        or os.getenv("https_proxy")
        or os.getenv("HTTP_PROXY")
        or os.getenv("http_proxy")
    )
    trend_browser_mode: str = Field(default=os.getenv("TREND_BROWSER_MODE", "isolated"))
    trend_browser_cdp_url: str | None = Field(default=os.getenv("TREND_BROWSER_CDP_URL"))
    trend_browser_executable_path: str | None = Field(default=os.getenv("TREND_BROWSER_EXECUTABLE_PATH"))
    trend_browser_user_data_dir: str | None = Field(default=os.getenv("TREND_BROWSER_USER_DATA_DIR"))
    trend_browser_channel: str | None = Field(default=os.getenv("TREND_BROWSER_CHANNEL", "chrome"))
    trend_browser_extension_path: str | None = Field(default=os.getenv("TREND_BROWSER_EXTENSION_PATH"))
    trend_batch_delay_min_seconds: int = Field(default_factory=lambda: _get_int_env("TREND_BATCH_DELAY_MIN_SECONDS", 4))
    trend_batch_delay_max_seconds: int = Field(default_factory=lambda: _get_int_env("TREND_BATCH_DELAY_MAX_SECONDS", 9))
    trend_block_cooldown_base_seconds: int = Field(
        default_factory=lambda: _get_int_env("TREND_BLOCK_COOLDOWN_BASE_SECONDS", 20)
    )
    trend_block_cooldown_max_seconds: int = Field(
        default_factory=lambda: _get_int_env("TREND_BLOCK_COOLDOWN_MAX_SECONDS", 90)
    )
    sitemap_http_timeout_seconds: int = Field(default_factory=lambda: _get_int_env("SITEMAP_HTTP_TIMEOUT_SECONDS", 30))
    sitemap_max_files: int = Field(default_factory=lambda: _get_int_env("SITEMAP_MAX_FILES", 2000))
    sitemap_scheduler_poll_seconds: int = Field(default_factory=lambda: _get_int_env("SITEMAP_SCHEDULER_POLL_SECONDS", 30))
    sitemap_scheduler_batch_size: int = Field(default_factory=lambda: _get_int_env("SITEMAP_SCHEDULER_BATCH_SIZE", 20))


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    settings = AppSettings()
    if settings.app_env.lower() == "production":
        settings.docs_url = None
        settings.redoc_url = None
    return settings
