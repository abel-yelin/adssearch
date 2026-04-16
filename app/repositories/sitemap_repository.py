from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.statuses import SitemapMonitorStatus, SitemapRunStatus
from app.models.sitemap_monitor import SitemapMonitor
from app.models.sitemap_run import SitemapRun


class SitemapRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_monitor(self, *, monitor_id: str, payload: dict, sitemap_url: str) -> SitemapMonitor:
        now = datetime.now(UTC)
        monitor = SitemapMonitor(
            id=monitor_id,
            site_url=payload["site_url"],
            sitemap_url=sitemap_url,
            interval_minutes=payload["interval_minutes"],
            enabled=payload.get("enabled", True),
            status=SitemapMonitorStatus.IDLE.value,
            request_payload=payload,
            next_check_at=now if payload.get("enabled", True) else None,
        )
        self.session.add(monitor)
        self.session.flush()
        return monitor

    def get_monitor(self, monitor_id: str) -> SitemapMonitor | None:
        stmt = select(SitemapMonitor).where(SitemapMonitor.id == monitor_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def list_monitors(self) -> list[SitemapMonitor]:
        stmt = select(SitemapMonitor).order_by(SitemapMonitor.created_at.desc())
        return list(self.session.execute(stmt).scalars().all())

    def list_due_monitors(self, now: datetime, limit: int) -> list[SitemapMonitor]:
        stmt = (
            select(SitemapMonitor)
            .where(
                SitemapMonitor.enabled.is_(True),
                SitemapMonitor.next_check_at.is_not(None),
                SitemapMonitor.next_check_at <= now,
            )
            .order_by(SitemapMonitor.next_check_at.asc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars().all())

    def has_active_run(self, monitor_id: str) -> bool:
        stmt = select(SitemapRun.id).where(
            SitemapRun.monitor_id == monitor_id,
            SitemapRun.status.in_((SitemapRunStatus.PENDING.value, SitemapRunStatus.RUNNING.value)),
        )
        return self.session.execute(stmt).first() is not None

    def create_run(self, *, run_id: str, monitor_id: str, trigger_mode: str) -> SitemapRun:
        run = SitemapRun(
            id=run_id,
            monitor_id=monitor_id,
            trigger_mode=trigger_mode,
            status=SitemapRunStatus.PENDING.value,
        )
        self.session.add(run)
        monitor = self.get_monitor(monitor_id)
        if monitor is not None:
            monitor.status = SitemapMonitorStatus.QUEUED.value
            monitor.updated_at = datetime.now(UTC)
            self.session.add(monitor)
        self.session.flush()
        return run

    def get_run(self, run_id: str) -> SitemapRun | None:
        stmt = select(SitemapRun).where(SitemapRun.id == run_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def get_latest_run(self, monitor_id: str) -> SitemapRun | None:
        stmt = (
            select(SitemapRun)
            .where(SitemapRun.monitor_id == monitor_id)
            .order_by(SitemapRun.created_at.desc())
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def get_latest_successful_run(self, monitor_id: str) -> SitemapRun | None:
        stmt = (
            select(SitemapRun)
            .where(
                SitemapRun.monitor_id == monitor_id,
                SitemapRun.status == SitemapRunStatus.COMPLETED.value,
            )
            .order_by(SitemapRun.finished_at.desc(), SitemapRun.created_at.desc())
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def set_run_status(
        self,
        run_id: str,
        status: str,
        *,
        result_payload: dict | None = None,
        snapshot_payload: dict | None = None,
        error_message: str | None = None,
        started: bool = False,
        finished: bool = False,
    ) -> SitemapRun | None:
        run = self.get_run(run_id)
        if run is None:
            return None

        now = datetime.now(UTC)
        run.status = status
        run.updated_at = now
        run.error_message = error_message
        if result_payload is not None:
            run.result_payload = result_payload
            summary = (result_payload or {}).get("summary", {})
            if isinstance(summary, dict):
                run.new_url_count = summary.get("new_url_count")
                run.deleted_url_count = summary.get("deleted_url_count")
                run.lastmod_changed_count = summary.get("lastmod_changed_count")
                run.tracked_url_count = summary.get("tracked_url_count")
        if snapshot_payload is not None:
            run.snapshot_payload = snapshot_payload
        if started and run.started_at is None:
            run.started_at = now
        if finished:
            run.finished_at = now
        self.session.add(run)
        self.session.flush()
        return run

    def mark_monitor_running(self, monitor_id: str) -> SitemapMonitor | None:
        monitor = self.get_monitor(monitor_id)
        if monitor is None:
            return None
        monitor.status = SitemapMonitorStatus.RUNNING.value
        monitor.updated_at = datetime.now(UTC)
        self.session.add(monitor)
        self.session.flush()
        return monitor

    def finalize_monitor_success(self, monitor_id: str, *, snapshot: dict, result: dict) -> SitemapMonitor | None:
        monitor = self.get_monitor(monitor_id)
        if monitor is None:
            return None
        now = datetime.now(UTC)
        monitor.status = SitemapMonitorStatus.COMPLETED.value
        monitor.latest_result = result
        monitor.last_snapshot = None
        monitor.last_checked_at = now
        monitor.last_success_at = now
        monitor.last_error = None
        monitor.next_check_at = now + timedelta(minutes=monitor.interval_minutes) if monitor.enabled else None
        monitor.updated_at = now
        self.session.add(monitor)
        self.session.flush()
        return monitor

    def finalize_monitor_failure(self, monitor_id: str, error_message: str) -> SitemapMonitor | None:
        monitor = self.get_monitor(monitor_id)
        if monitor is None:
            return None
        now = datetime.now(UTC)
        monitor.status = SitemapMonitorStatus.FAILED.value
        monitor.last_error = error_message
        monitor.last_checked_at = now
        monitor.next_check_at = now + timedelta(minutes=monitor.interval_minutes) if monitor.enabled else None
        monitor.updated_at = now
        self.session.add(monitor)
        self.session.flush()
        return monitor
