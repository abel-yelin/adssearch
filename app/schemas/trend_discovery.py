from typing import Literal

from pydantic import BaseModel, Field, model_validator


TrendDiscoveryTimeRange = Literal["today 12-m", "today 3-m", "today 1-m", "now 7-d"]
TrendSignalType = Literal["breakout", "surging", "steady-rise"]


class TrendDiscoveryRequest(BaseModel):
    keywords: list[str] = Field(default_factory=list, description="Explicit keyword list to scan.")
    keyword_blob: str | None = Field(
        default=None,
        description="Comma/newline separated keyword roots. Useful for large pasted lists.",
    )
    time_range: TrendDiscoveryTimeRange = Field(default="today 3-m")
    geo: str = Field(default="", description="Google Trends geo parameter. Empty means worldwide.")
    language: str = Field(default="en-US", description="Google Trends language, for example en-US.")
    timezone_offset: int = Field(default=0, description="Google Trends tz parameter in minutes.")
    batch_size: int = Field(default=5, ge=1, le=5, description="Free-mode scan batch size. Google Trends supports up to 5.")
    recent_window: int = Field(default=4, ge=2, le=12)
    baseline_window: int = Field(default=8, ge=4, le=52)
    min_growth_ratio: float = Field(default=1.5, ge=1.0)
    min_absolute_gain: float = Field(default=8.0, ge=0.0)
    min_recent_avg: float = Field(default=5.0, ge=0.0)
    top_n: int = Field(default=20, ge=1, le=200)
    batch_delay_seconds: float = Field(default=2.0, ge=0.0, le=30.0)

    @model_validator(mode="after")
    def validate_keyword_input(self) -> "TrendDiscoveryRequest":
        if not self.keywords and not (self.keyword_blob or "").strip():
            raise ValueError("Either 'keywords' or 'keyword_blob' must be provided.")
        if self.baseline_window <= self.recent_window:
            raise ValueError("baseline_window must be greater than recent_window.")
        return self


class TrendDiscoveryBatchResponse(BaseModel):
    batch_no: int
    keywords: list[str]
    data_points: int
    returned_keywords: list[str]


class TrendDiscoveryRiserResponse(BaseModel):
    keyword: str
    signal: TrendSignalType
    batch_no: int
    latest_value: int
    recent_avg: float
    baseline_avg: float
    absolute_gain: float
    growth_ratio: float
    slope: float
    score: float


class TrendDiscoveryResponse(BaseModel):
    keyword_count: int
    scanned_keyword_count: int
    batch_count: int
    batch_size: int
    time_range: TrendDiscoveryTimeRange
    geo: str
    risers: list[TrendDiscoveryRiserResponse]
    batches: list[TrendDiscoveryBatchResponse]
    notes: list[str]
