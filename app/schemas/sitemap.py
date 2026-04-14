from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator


SitemapMonitorStatus = Literal["idle", "queued", "running", "completed", "failed", "paused"]
SitemapRunStatus = Literal["pending", "running", "completed", "failed", "cancelled"]
TriggerMode = Literal["manual", "scheduled"]


class SitemapMonitorCreateRequest(BaseModel):
    site_url: HttpUrl
    sitemap_url: HttpUrl | None = None
    interval_minutes: int = Field(..., description="Only supports 5, 30, 60.")
    enabled: bool = True

    @field_validator("interval_minutes")
    @classmethod
    def validate_interval(cls, value: int) -> int:
        if value not in {5, 30, 60}:
            raise ValueError("interval_minutes must be one of 5, 30, 60.")
        return value


class SitemapMonitorCreateResponse(BaseModel):
    monitor_id: str
    status: SitemapMonitorStatus
    sitemap_url: str
    next_check_at: datetime | None = None


class SitemapRunDispatchResponse(BaseModel):
    monitor_id: str
    run_id: str
    status: SitemapRunStatus
    trigger_mode: TriggerMode
    message: str


class SitemapUrlChange(BaseModel):
    url: str
    lastmod: str | None = None
    source_sitemap: str | None = None


class SitemapLastmodChange(BaseModel):
    url: str
    previous_lastmod: str | None = None
    current_lastmod: str | None = None
    source_sitemap: str | None = None


class SitemapRunResponse(BaseModel):
    run_id: str
    monitor_id: str
    trigger_mode: TriggerMode
    status: SitemapRunStatus
    result: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class SitemapMonitorResponse(BaseModel):
    monitor_id: str
    site_url: str
    sitemap_url: str
    interval_minutes: int
    enabled: bool
    status: SitemapMonitorStatus
    latest_run_id: str | None = None
    last_checked_at: datetime | None = None
    last_success_at: datetime | None = None
    next_check_at: datetime | None = None
    latest_result: dict[str, Any] | None = None
    last_error: str | None = None


class SitemapMonitorListResponse(BaseModel):
    items: list[SitemapMonitorResponse]


class SitemapRecentUrlsResponse(BaseModel):
    monitor_id: str
    site_url: str
    sitemap_url: str
    latest_new_urls: list[SitemapUrlChange]
    summary: dict[str, Any]
