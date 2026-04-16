from contextlib import contextmanager
from types import SimpleNamespace
from uuid import UUID

from app.services.ads_task_service import AdsTaskService


class DummyJob:
    def __init__(self):
        self.meta = {}

    def save_meta(self):
        return None


class DummyQueueService:
    def __init__(self):
        self.settings = SimpleNamespace(queue_default_retry_count=1)
        self.enqueued = []

    def fetch_job(self, task_id):
        return None

    def enqueue(self, func_path, payload, job_id):
        self.enqueued.append((func_path, payload, job_id))
        return DummyJob()

    def stop_job(self, job_id):
        return None


class FakeRepo:
    task = None
    updates = []
    created = []

    def __init__(self, session):
        self.session = session

    def get_by_task_id(self, task_id):
        return self.task

    def update_status(self, task_id, status, **kwargs):
        self.updates.append((task_id, status, kwargs))
        if self.task is not None:
            self.task.status = status
            if "retry_count" in kwargs and kwargs["retry_count"] is not None:
                self.task.retry_count = kwargs["retry_count"]

    def create_task(self, **kwargs):
        self.created.append(kwargs)


@contextmanager
def fake_db_session():
    yield object()


def test_get_task_status_uses_database_state_when_queue_job_missing(monkeypatch):
    import app.services.ads_task_service as module

    FakeRepo.task = SimpleNamespace(
        status="completed",
        retry_count=1,
        result_payload={"success": True},
        error_message=None,
    )
    FakeRepo.updates = []
    FakeRepo.created = []

    monkeypatch.setattr(module, "get_db_session", fake_db_session)
    monkeypatch.setattr(module, "TaskRepository", FakeRepo)

    service = AdsTaskService(DummyQueueService())
    result = service.get_task_status("task-123")

    assert result.status == "completed"
    assert result.result == {"success": True}
    assert result.retries_left == 1


def test_cancel_task_succeeds_without_active_queue_job(monkeypatch):
    import app.services.ads_task_service as module

    FakeRepo.task = SimpleNamespace(
        status="pending",
        retry_count=1,
        result_payload=None,
        error_message=None,
    )
    FakeRepo.updates = []
    FakeRepo.created = []

    monkeypatch.setattr(module, "get_db_session", fake_db_session)
    monkeypatch.setattr(module, "TaskRepository", FakeRepo)

    service = AdsTaskService(DummyQueueService())
    result = service.cancel_task("task-123")

    assert result.success is True
    assert result.status == "cancelled"
    assert FakeRepo.updates[0][1] == "cancelled"


def test_retry_task_uses_database_payload_when_queue_job_missing(monkeypatch):
    import app.services.ads_task_service as module

    FakeRepo.task = SimpleNamespace(
        status="failed",
        retry_count=2,
        request_payload={"domain": "example.com", "region": "US"},
        result_payload=None,
        error_message="boom",
    )
    FakeRepo.updates = []
    FakeRepo.created = []

    monkeypatch.setattr(module, "get_db_session", fake_db_session)
    monkeypatch.setattr(module, "TaskRepository", FakeRepo)
    monkeypatch.setattr(module.uuid, "uuid4", lambda: UUID("00000000-0000-0000-0000-000000000999"))

    queue_service = DummyQueueService()
    service = AdsTaskService(queue_service)
    result = service.retry_task("task-123")

    assert result.success is True
    assert result.status == "pending"
    assert result.new_task_id == "00000000-0000-0000-0000-000000000999"
    assert FakeRepo.updates[0][1] == "failed"
    assert FakeRepo.created[0]["status"] == "pending"
    assert queue_service.enqueued[0][2] == "00000000-0000-0000-0000-000000000999"
