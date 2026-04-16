from pydantic import BaseModel, ConfigDict, Field


class FreeTrendsSeedItem(BaseModel):
    id: int
    term: str
    normalized_term: str
    group_key: str | None = None
    enabled: bool = True
    priority: int = 100
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None
    cooldown_until: str | None = None
    last_scanned_at: str | None = None
    last_status: str | None = None
    created_at: str
    updated_at: str


class FreeTrendsSeedsResponse(BaseModel):
    items: list[FreeTrendsSeedItem]


class FreeTrendsSeedsListResponse(BaseModel):
    items: list[FreeTrendsSeedItem]
    total: int
    page: int
    page_size: int
    search: str | None = None
    group_key: str | None = None
    enabled: bool | None = None
    sort_by: str
    sort_order: str


class FreeTrendsSeedCreateRequest(BaseModel):
    term: str = Field(..., min_length=1)
    group_key: str | None = None
    enabled: bool = True
    priority: int = 100
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None


class FreeTrendsSeedUpdateRequest(BaseModel):
    term: str = Field(..., min_length=1)
    group_key: str | None = None
    enabled: bool = True
    priority: int = 100
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None


class FreeTrendsSeedsReplaceRequest(BaseModel):
    root_terms: list[str] = Field(..., min_length=1)


class FreeTrendsSeedsBulkReplaceRequest(BaseModel):
    items: list[FreeTrendsSeedCreateRequest] = Field(..., min_length=1)


class FreeTrendsSeedDeleteResponse(BaseModel):
    deleted: bool
    seed_id: int


class FreeTrendsOutputPaths(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    json_path: str = Field(alias="json")
    csv_path: str = Field(alias="csv")
    latest_csv_path: str = Field(alias="latest_csv")


class FreeTrendsRunSummaryResponse(BaseModel):
    run_id: str
    status: str
    started_at: str
    finished_at: str | None = None
    new_keyword_count: int
    output_paths: FreeTrendsOutputPaths | None = None
    blocked_message: str | None = None
    error_message: str | None = None


class FreeTrendsResultItem(BaseModel):
    run_id: str
    normalized_term: str
    term: str
    source_term: str
    source_terms: list[str]
    depth: int
    discovered_at: str
    batch_id: str
    region: str
    time_range: str
    trend_type: str
    value_label: str


class FreeTrendsRunResultsResponse(BaseModel):
    run_id: str
    items: list[FreeTrendsResultItem]


class FreeTrendsStatusResponse(BaseModel):
    config_path: str
    schedule_time: str
    timezone: str
    latest_run: FreeTrendsRunSummaryResponse | None = None
