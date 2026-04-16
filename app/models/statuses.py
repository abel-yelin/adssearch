from __future__ import annotations

from enum import StrEnum


class SearchTaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SearchTaskLookupStatus(StrEnum):
    PENDING = SearchTaskStatus.PENDING
    RUNNING = SearchTaskStatus.RUNNING
    COMPLETED = SearchTaskStatus.COMPLETED
    FAILED = SearchTaskStatus.FAILED
    CANCELLED = SearchTaskStatus.CANCELLED
    UNKNOWN = "unknown"


class TrendTaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    RETRYING = "retrying"
    COOLDOWN = "cooldown"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskBatchStatus(StrEnum):
    RUNNING = "running"
    RETRYING = "retrying"
    COOLDOWN = "cooldown"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskKeywordStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PROCESSED = "processed"
    SKIPPED = "skipped"


class TaskKeywordSourceType(StrEnum):
    SEED = "seed"
    RELATED = "related"


class SitemapMonitorStatus(StrEnum):
    IDLE = "idle"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class SitemapRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SitemapTriggerMode(StrEnum):
    MANUAL = "manual"
    SCHEDULED = "scheduled"


def enum_values(enum_cls: type[StrEnum]) -> tuple[str, ...]:
    return tuple(item.value for item in enum_cls)
