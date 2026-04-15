from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


TrendTimeRange = Literal["today 12-m", "today 3-m", "today 1-m", "now 7-d"]
TrendTaskStatus = Literal[
    "pending",
    "running",
    "retrying",
    "cooldown",
    "completed",
    "failed",
    "cancelled",
]
KeywordStatus = Literal["queued", "running", "processed", "skipped"]


class TrendTaskCreateRequest(BaseModel):
    base_keyword: str = Field(..., min_length=1, max_length=100)
    seed_keywords: list[str] = Field(..., min_length=1)
    time_range: TrendTimeRange
    threshold: int = Field(..., ge=1)
    max_keywords: int = Field(..., ge=1, le=5000)
    geo: str = Field(default="", description="Google Trends geo 参数，默认全局")
    language: str = Field(default="en-US", description="Playwright 页面语言")
    timezone_offset: int = Field(default=0, description="Google Trends tz 参数，单位分钟")
    proxy: str | None = Field(default=None)
    browser_mode: Literal["isolated", "cdp", "persistent"] = Field(default="isolated")
    browser_cdp_url: str | None = Field(default=None)
    browser_executable_path: str | None = Field(default=None)
    browser_user_data_dir: str | None = Field(default=None)


class TrendTaskCreateResponse(BaseModel):
    task_id: str
    status: Literal["pending"]


class TrendTaskSummaryItem(BaseModel):
    keyword: str
    score_percent: float
    source_batch_no: int


class TrendTaskStatusResponse(BaseModel):
    task_id: str
    status: TrendTaskStatus
    base_keyword: str
    seed_keywords: list[str]
    time_range: TrendTimeRange
    threshold: int
    max_keywords: int
    processed_keywords_count: int
    effective_keywords_count: int
    current_batch_no: int
    retries: int
    recent_error: str | None = None
    error_code: str | None = None
    result: dict[str, Any] | None = None
    updated_at: datetime


class TrendTaskSummaryResponse(BaseModel):
    task_id: str
    status: TrendTaskStatus
    processed_keywords_count: int
    effective_keywords_count: int
    current_batch_no: int
    top_effective_keywords: list[TrendTaskSummaryItem]
    updated_at: datetime


class TrendTaskActionResponse(BaseModel):
    task_id: str
    status: TrendTaskStatus
    message: str
    new_task_id: str | None = None


class TrendTaskExportResponse(BaseModel):
    task_id: str
    base_keyword: str
    time_range: TrendTimeRange
    threshold: int
    max_keywords: int
    status: TrendTaskStatus
    effective_new_words: list[dict[str, Any]]
    processed_keywords: list[str]
    pending_keywords: list[str]
    skipped_keywords: list[dict[str, Any]]
    all_captured_data: list[dict[str, Any]]
    statistics: dict[str, Any]
