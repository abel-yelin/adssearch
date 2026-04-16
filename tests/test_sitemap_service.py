from contextlib import contextmanager
from types import SimpleNamespace

from app.services.sitemap_service import SitemapService


@contextmanager
def fake_db_session():
    yield object()


class FakeRepo:
    monitor = None
    run = None
    latest_successful_run = None
    set_run_status_calls = []

    def __init__(self, session):
        self.session = session

    def get_monitor(self, monitor_id):
        return self.monitor

    def get_run(self, run_id):
        return self.run

    def get_latest_successful_run(self, monitor_id):
        return self.latest_successful_run

    def set_run_status(self, run_id, status, **kwargs):
        self.set_run_status_calls.append((run_id, status, kwargs))

    def mark_monitor_running(self, monitor_id):
        return None

    def finalize_monitor_success(self, monitor_id, *, snapshot, result):
        return None

    def finalize_monitor_failure(self, monitor_id, error_message):
        return None


class FakeFetcher:
    previous_snapshot = None

    def __init__(self, timeout_seconds, max_files):
        self.timeout_seconds = timeout_seconds
        self.max_files = max_files

    def fetch_snapshot(self, sitemap_url, previous_snapshot):
        FakeFetcher.previous_snapshot = previous_snapshot
        return (
            {
                "url_entries": {
                    "https://example.com/new": {
                        "lastmod": "2026-04-16",
                        "source_sitemap": sitemap_url,
                    }
                },
                "files": {},
            },
            {"file_count": 1, "url_count": 1},
        )


def test_execute_run_uses_latest_successful_run_snapshot(monkeypatch):
    import app.services.sitemap_service as module

    FakeRepo.monitor = SimpleNamespace(
        id="monitor-1",
        site_url="https://example.com",
        sitemap_url="https://example.com/sitemap.xml",
        last_snapshot={"legacy": True},
    )
    FakeRepo.run = SimpleNamespace(id="run-1")
    FakeRepo.latest_successful_run = SimpleNamespace(snapshot_payload={"from_run": True})
    FakeRepo.set_run_status_calls = []
    FakeFetcher.previous_snapshot = None

    monkeypatch.setattr(module, "get_db_session", fake_db_session)
    monkeypatch.setattr(module, "SitemapRepository", FakeRepo)
    monkeypatch.setattr(module, "SitemapFetcher", FakeFetcher)

    settings = SimpleNamespace(sitemap_http_timeout_seconds=30, sitemap_max_files=100)
    service = SitemapService(queue_service=SimpleNamespace(), settings=settings)
    result = service.execute_run("monitor-1", "run-1")

    assert FakeFetcher.previous_snapshot == {"from_run": True}
    assert result["summary"]["new_url_count"] == 1
    assert FakeRepo.set_run_status_calls[1][1] == "completed"
    assert FakeRepo.set_run_status_calls[1][2]["snapshot_payload"]["url_entries"]["https://example.com/new"]["lastmod"] == "2026-04-16"
