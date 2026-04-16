from __future__ import annotations

import json
import uuid

from app.core.config import AppSettings
from app.free_trends.config import load_config
from app.free_trends.service import build_live_service
from app.free_trends.storage import FreeTrendsStorage
from app.free_trends.storage import utcnow
from app.schemas.free_trends_requests import FreeTrendsRunRequestResponse
from app.schemas.free_trends import (
    FreeTrendsResultItem,
    FreeTrendsRunResultsResponse,
    FreeTrendsRunSummaryResponse,
    FreeTrendsSeedCreateRequest,
    FreeTrendsSeedDeleteResponse,
    FreeTrendsSeedsListResponse,
    FreeTrendsSeedsResponse,
    FreeTrendsSeedItem,
    FreeTrendsSeedUpdateRequest,
    FreeTrendsStatusResponse,
)


class FreeTrendsApiService:
    def __init__(self, settings: AppSettings):
        self.settings = settings
        self.config = load_config(settings.free_trends_config_path)
        self.storage = FreeTrendsStorage(self.config.database_path)

    def get_status(self) -> FreeTrendsStatusResponse:
        latest = self.storage.get_latest_run_summary()
        return FreeTrendsStatusResponse(
            config_path=self.settings.free_trends_config_path,
            schedule_time=self.config.schedule_time,
            timezone=self.config.timezone,
            latest_run=self._map_run_summary(latest) if latest else None,
        )

    def list_seeds(
        self,
        *,
        search: str | None = None,
        group_key: str | None = None,
        enabled: bool | None = None,
        page: int = 1,
        page_size: int = 50,
        sort_by: str = "priority",
        sort_order: str = "desc",
    ) -> FreeTrendsSeedsListResponse:
        rows, total = self.storage.query_seed_terms(
            search=search,
            group_key=group_key,
            enabled=enabled,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        return FreeTrendsSeedsListResponse(
            items=[self._map_seed(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
            search=search,
            group_key=group_key,
            enabled=enabled,
            sort_by=sort_by,
            sort_order=sort_order,
        )

    def replace_seeds(self, terms: list[str]) -> FreeTrendsSeedsResponse:
        self.storage.replace_seed_terms(terms)
        self.config.root_terms = terms
        list_response = self.list_seeds(page=1, page_size=max(len(terms), 1))
        return FreeTrendsSeedsResponse(items=list_response.items)

    def create_seed(self, request: FreeTrendsSeedCreateRequest) -> FreeTrendsSeedItem:
        row = self.storage.create_seed_term(
            term=request.term,
            group_key=request.group_key,
            enabled=request.enabled,
            priority=request.priority,
            tags=request.tags,
            notes=request.notes,
        )
        return self._map_seed(row)

    def update_seed(self, seed_id: int, request: FreeTrendsSeedUpdateRequest) -> FreeTrendsSeedItem:
        row = self.storage.update_seed_term(
            seed_id,
            term=request.term,
            group_key=request.group_key,
            enabled=request.enabled,
            priority=request.priority,
            tags=request.tags,
            notes=request.notes,
        )
        return self._map_seed(row)

    def delete_seed(self, seed_id: int) -> FreeTrendsSeedDeleteResponse:
        deleted = self.storage.delete_seed_term(seed_id)
        if not deleted:
            raise ValueError(f"Seed term '{seed_id}' not found.")
        return FreeTrendsSeedDeleteResponse(deleted=True, seed_id=seed_id)

    def bulk_replace_seed_items(self, items: list[FreeTrendsSeedCreateRequest]) -> FreeTrendsSeedsResponse:
        rows = self.storage.bulk_replace_seed_terms([item.model_dump() for item in items])
        self.config.root_terms = [row.term for row in rows]
        return FreeTrendsSeedsResponse(items=[self._map_seed(row) for row in rows])

    def get_latest_run(self) -> FreeTrendsRunSummaryResponse:
        latest = self.storage.get_latest_run_summary()
        if latest is None:
            raise ValueError("No free trends run has been recorded yet.")
        return self._map_run_summary(latest)

    def get_run(self, run_id: str) -> FreeTrendsRunSummaryResponse:
        payload = self.storage.get_run_summary(run_id)
        if payload is None:
            raise ValueError(f"Free trends run '{run_id}' not found.")
        return self._map_run_summary(payload)

    def get_run_results(self, run_id: str) -> FreeTrendsRunResultsResponse:
        run_payload = self.storage.get_run_summary(run_id)
        if run_payload is None:
            raise ValueError(f"Free trends run '{run_id}' not found.")
        items = self.storage.list_discovered_terms_for_run(run_id)
        return FreeTrendsRunResultsResponse(
            run_id=run_id,
            items=[FreeTrendsResultItem(**item) for item in items],
        )

    async def trigger_run(self) -> FreeTrendsRunSummaryResponse:
        service = build_live_service(self.config)
        await service.collector.start()
        try:
            summary = await service.run_once()
        finally:
            await service.collector.close()
        return FreeTrendsRunSummaryResponse(**summary)

    def create_run_request(self) -> FreeTrendsRunRequestResponse:
        request_id = uuid.uuid4().hex
        requested_at = utcnow()
        self.storage.create_run_request(request_id, requested_at)
        payload = self.storage.get_run_request(request_id)
        assert payload is not None
        return FreeTrendsRunRequestResponse(**payload)

    def get_run_request(self, request_id: str) -> FreeTrendsRunRequestResponse:
        payload = self.storage.get_run_request(request_id)
        if payload is None:
            raise ValueError(f"Free trends run request '{request_id}' not found.")
        return FreeTrendsRunRequestResponse(**payload)

    @staticmethod
    def _map_run_summary(payload: dict) -> FreeTrendsRunSummaryResponse:
        return FreeTrendsRunSummaryResponse(
            run_id=payload["run_id"],
            status=payload["status"],
            started_at=payload["started_at"],
            finished_at=payload.get("finished_at"),
            new_keyword_count=int(payload.get("new_keyword_count") or 0),
            output_paths=payload.get("output_paths")
            or {
                "json": payload.get("output_json_path") or "",
                "csv": payload.get("output_csv_path") or "",
                "latest_csv": payload.get("latest_csv_path") or "",
            },
            blocked_message=payload.get("blocked_message"),
            error_message=payload.get("error_message"),
        )

    @staticmethod
    def _map_seed(row) -> FreeTrendsSeedItem:
        return FreeTrendsSeedItem(
            id=row.id,
            term=row.term,
            normalized_term=row.normalized_term,
            group_key=row.group_key,
            enabled=row.enabled,
            priority=row.priority,
            tags=[] if not row.tags_json else json.loads(row.tags_json),
            notes=row.notes,
            cooldown_until=row.cooldown_until,
            last_scanned_at=row.last_scanned_at,
            last_status=row.last_status,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
