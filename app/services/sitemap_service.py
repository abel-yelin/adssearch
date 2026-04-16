import uuid
from datetime import UTC, datetime

from app.core.config import AppSettings
from app.db.session import get_db_session
from app.models.statuses import SitemapRunStatus, SitemapTriggerMode
from app.repositories.sitemap_repository import SitemapRepository
from app.schemas.sitemap import (
    SitemapMonitorCreateRequest,
    SitemapMonitorCreateResponse,
    SitemapMonitorListResponse,
    SitemapMonitorResponse,
    SitemapRecentUrlsResponse,
    SitemapRunDispatchResponse,
    SitemapRunResponse,
)
from app.services.queue_service import TaskQueueService
from app.services.sitemap_fetcher import SitemapFetcher


class SitemapService:
    def __init__(self, queue_service: TaskQueueService, settings: AppSettings):
        self.queue_service = queue_service
        self.settings = settings

    def create_monitor(self, request: SitemapMonitorCreateRequest) -> SitemapMonitorCreateResponse:
        payload = request.model_dump(mode="json")
        sitemap_url = payload.get("sitemap_url") or SitemapFetcher(
            timeout_seconds=self.settings.sitemap_http_timeout_seconds,
            max_files=self.settings.sitemap_max_files,
        ).discover_sitemap_url(payload["site_url"])
        monitor_id = str(uuid.uuid4())
        with get_db_session() as session:
            monitor = SitemapRepository(session).create_monitor(
                monitor_id=monitor_id,
                payload=payload,
                sitemap_url=sitemap_url,
            )
        return SitemapMonitorCreateResponse(
            monitor_id=monitor.id,
            status=monitor.status,
            sitemap_url=monitor.sitemap_url,
            next_check_at=monitor.next_check_at,
        )

    def list_monitors(self) -> SitemapMonitorListResponse:
        with get_db_session() as session:
            repo = SitemapRepository(session)
            monitors = repo.list_monitors()
            runs = {monitor.id: repo.get_latest_run(monitor.id) for monitor in monitors}
        return SitemapMonitorListResponse(
            items=[self._to_monitor_response(monitor, runs.get(monitor.id)) for monitor in monitors]
        )

    def get_monitor(self, monitor_id: str) -> SitemapMonitorResponse:
        with get_db_session() as session:
            repo = SitemapRepository(session)
            monitor = repo.get_monitor(monitor_id)
            latest_run = repo.get_latest_run(monitor_id) if monitor else None
        if monitor is None:
            raise ValueError(f"Monitor '{monitor_id}' not found.")
        return self._to_monitor_response(monitor, latest_run)

    def dispatch_run(self, monitor_id: str, trigger_mode: str = SitemapTriggerMode.MANUAL.value) -> SitemapRunDispatchResponse:
        run_id = str(uuid.uuid4())
        with get_db_session() as session:
            repo = SitemapRepository(session)
            monitor = repo.get_monitor(monitor_id)
            if monitor is None:
                raise ValueError(f"Monitor '{monitor_id}' not found.")
            if repo.has_active_run(monitor_id):
                raise ValueError(f"Monitor '{monitor_id}' already has an active run.")
            repo.create_run(run_id=run_id, monitor_id=monitor_id, trigger_mode=trigger_mode)

        self.queue_service.enqueue(
            "app.tasks.sitemap_tasks.run_sitemap_monitor_task",
            {"monitor_id": monitor_id, "run_id": run_id},
            job_id=run_id,
        )
        return SitemapRunDispatchResponse(
            monitor_id=monitor_id,
            run_id=run_id,
            status=SitemapRunStatus.PENDING,
            trigger_mode=trigger_mode,
            message="Sitemap monitor task queued successfully.",
        )

    def get_run(self, run_id: str) -> SitemapRunResponse:
        with get_db_session() as session:
            run = SitemapRepository(session).get_run(run_id)
        if run is None:
            raise ValueError(f"Run '{run_id}' not found.")
        return SitemapRunResponse(
            run_id=run.id,
            monitor_id=run.monitor_id,
            trigger_mode=run.trigger_mode,
            status=run.status,
            result=run.result_payload,
            error_message=run.error_message,
            created_at=run.created_at,
            updated_at=run.updated_at,
            started_at=run.started_at,
            finished_at=run.finished_at,
        )

    def get_recent_new_urls(self, monitor_id: str) -> SitemapRecentUrlsResponse:
        with get_db_session() as session:
            monitor = SitemapRepository(session).get_monitor(monitor_id)
        if monitor is None:
            raise ValueError(f"Monitor '{monitor_id}' not found.")
        latest_result = monitor.latest_result or {}
        return SitemapRecentUrlsResponse(
            monitor_id=monitor.id,
            site_url=monitor.site_url,
            sitemap_url=monitor.sitemap_url,
            latest_new_urls=latest_result.get("new_urls", []),
            summary=latest_result.get("summary", {}),
        )

    def execute_run(self, monitor_id: str, run_id: str) -> dict:
        with get_db_session() as session:
            repo = SitemapRepository(session)
            monitor = repo.get_monitor(monitor_id)
            run = repo.get_run(run_id)
            if monitor is None:
                raise ValueError(f"Monitor '{monitor_id}' not found.")
            if run is None:
                raise ValueError(f"Run '{run_id}' not found.")
            repo.set_run_status(run_id, SitemapRunStatus.RUNNING.value, started=True)
            repo.mark_monitor_running(monitor_id)
            latest_successful_run = repo.get_latest_successful_run(monitor_id)
            previous_snapshot = (
                latest_successful_run.snapshot_payload
                if latest_successful_run and latest_successful_run.snapshot_payload is not None
                else monitor.last_snapshot
            )
            sitemap_url = monitor.sitemap_url
            site_url = monitor.site_url

        fetcher = SitemapFetcher(
            timeout_seconds=self.settings.sitemap_http_timeout_seconds,
            max_files=self.settings.sitemap_max_files,
        )
        snapshot, stats = fetcher.fetch_snapshot(sitemap_url, previous_snapshot)
        result = self._build_run_result(monitor_id, site_url, sitemap_url, previous_snapshot, snapshot, stats)

        with get_db_session() as session:
            repo = SitemapRepository(session)
            repo.set_run_status(
                run_id,
                SitemapRunStatus.COMPLETED.value,
                result_payload=result,
                snapshot_payload=snapshot,
                finished=True,
            )
            repo.finalize_monitor_success(monitor_id, snapshot=snapshot, result=result)
        return result

    def fail_run(self, monitor_id: str, run_id: str, error_message: str) -> None:
        with get_db_session() as session:
            repo = SitemapRepository(session)
            repo.set_run_status(run_id, SitemapRunStatus.FAILED.value, error_message=error_message, finished=True)
            repo.finalize_monitor_failure(monitor_id, error_message)

    def _build_run_result(
        self,
        monitor_id: str,
        site_url: str,
        sitemap_url: str,
        previous_snapshot: dict | None,
        current_snapshot: dict,
        stats: dict,
    ) -> dict:
        previous_entries = (previous_snapshot or {}).get("url_entries", {})
        current_entries = current_snapshot.get("url_entries", {})
        previous_urls = set(previous_entries)
        current_urls = set(current_entries)

        baseline_created = previous_snapshot is None
        if baseline_created:
            new_urls = []
            deleted_urls = []
            lastmod_changed = []
        else:
            new_urls = [
                {
                    "url": url,
                    "lastmod": current_entries[url].get("lastmod"),
                    "source_sitemap": current_entries[url].get("source_sitemap"),
                }
                for url in sorted(current_urls - previous_urls)
            ]
            deleted_urls = [
                {
                    "url": url,
                    "lastmod": previous_entries[url].get("lastmod"),
                    "source_sitemap": previous_entries[url].get("source_sitemap"),
                }
                for url in sorted(previous_urls - current_urls)
            ]
            lastmod_changed = [
                {
                    "url": url,
                    "previous_lastmod": previous_entries[url].get("lastmod"),
                    "current_lastmod": current_entries[url].get("lastmod"),
                    "source_sitemap": current_entries[url].get("source_sitemap"),
                }
                for url in sorted(previous_urls & current_urls)
                if previous_entries[url].get("lastmod") != current_entries[url].get("lastmod")
            ]

        changed_sitemaps = [
            {"url": file_url, "content_hash": file_info.get("content_hash")}
            for file_url, file_info in current_snapshot.get("files", {}).items()
            if (previous_snapshot or {}).get("files", {}).get(file_url, {}).get("content_hash") != file_info.get("content_hash")
        ]

        return {
            "monitor_id": monitor_id,
            "site_url": site_url,
            "sitemap_url": sitemap_url,
            "checked_at": datetime.now(UTC).isoformat(),
            "baseline_created": baseline_created,
            "new_urls": new_urls,
            "deleted_urls": deleted_urls,
            "lastmod_changed": lastmod_changed,
            "changed_sitemaps": changed_sitemaps,
            "summary": {
                "new_url_count": len(new_urls),
                "deleted_url_count": len(deleted_urls),
                "lastmod_changed_count": len(lastmod_changed),
                "changed_sitemap_count": len(changed_sitemaps),
                "tracked_url_count": len(current_entries),
                **stats,
            },
        }

    def _to_monitor_response(self, monitor, latest_run) -> SitemapMonitorResponse:
        return SitemapMonitorResponse(
            monitor_id=monitor.id,
            site_url=monitor.site_url,
            sitemap_url=monitor.sitemap_url,
            interval_minutes=monitor.interval_minutes,
            enabled=monitor.enabled,
            status=monitor.status,
            latest_run_id=latest_run.id if latest_run else None,
            last_checked_at=monitor.last_checked_at,
            last_success_at=monitor.last_success_at,
            next_check_at=monitor.next_check_at,
            latest_result=monitor.latest_result,
            last_error=monitor.last_error,
        )
