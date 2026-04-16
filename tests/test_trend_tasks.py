from datetime import UTC, datetime

from app.dependencies.services import get_trend_task_service
from app.schemas.task import (
    TrendTaskActionResponse,
    TrendTaskCreateResponse,
    TrendTaskExportResponse,
    TrendTaskStatusResponse,
    TrendTaskSummaryResponse,
)


class FakeTrendTaskService:
    def create_task(self, request):
        return TrendTaskCreateResponse(task_id="trend-task-123", status="pending")

    def get_task_status(self, task_id):
        return TrendTaskStatusResponse(
            task_id=task_id,
            status="running",
            base_keyword="openai",
            seed_keywords=["chatgpt", "gpt-4"],
            time_range="today 12-m",
            threshold=20,
            max_keywords=100,
            batch_size=4,
            processed_keywords_count=8,
            effective_keywords_count=2,
            current_batch_no=2,
            retries=0,
            recent_error=None,
            error_code=None,
            result={"status": "running"},
            updated_at=datetime.now(UTC),
        )

    def get_task_summary(self, task_id):
        return TrendTaskSummaryResponse(
            task_id=task_id,
            status="completed",
            processed_keywords_count=12,
            effective_keywords_count=3,
            current_batch_no=3,
            top_effective_keywords=[
                {
                    "keyword": "chatgpt api",
                    "score_percent": 87.5,
                    "source_batch_no": 2,
                }
            ],
            updated_at=datetime.now(UTC),
        )

    def export_task(self, task_id):
        return TrendTaskExportResponse(
            task_id=task_id,
            base_keyword="openai",
            time_range="today 12-m",
            threshold=20,
            max_keywords=100,
            batch_size=4,
            status="completed",
            effective_new_words=[
                {
                    "keyword": "chatgpt api",
                    "score_percent": 87.5,
                    "first_five_all_zero": True,
                    "last_five_avg": 52.1,
                    "base_last_five_avg": 81.4,
                }
            ],
            processed_keywords=["chatgpt", "gpt-4"],
            pending_keywords=[],
            skipped_keywords=[],
            all_captured_data=[],
            statistics={
                "processed_keywords_count": 12,
                "effective_keywords_count": 3,
                "current_batch_no": 3,
                "retry_count": 0,
            },
        )

    def cancel_task(self, task_id):
        return TrendTaskActionResponse(
            task_id=task_id,
            status="cancelled",
            message="Task cancelled successfully.",
        )

    def retry_task(self, task_id):
        return TrendTaskActionResponse(
            task_id=task_id,
            new_task_id="trend-task-456",
            status="pending",
            message="Task retried successfully.",
        )


def test_create_trend_task_endpoint(client):
    from app.main import app

    app.dependency_overrides[get_trend_task_service] = lambda: FakeTrendTaskService()
    try:
        response = client.post(
            "/api/trends/tasks",
            json={
                "base_keyword": "openai",
                "seed_keywords": ["chatgpt", "gpt-4"],
                "time_range": "today 12-m",
                "threshold": 20,
                "max_keywords": 100,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    payload = response.json()
    assert payload["task_id"] == "trend-task-123"
    assert payload["status"] == "pending"


def test_get_trend_task_status_endpoint(client):
    from app.main import app

    app.dependency_overrides[get_trend_task_service] = lambda: FakeTrendTaskService()
    try:
        response = client.get("/api/trends/tasks/trend-task-123")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["task_id"] == "trend-task-123"
    assert payload["status"] == "running"
    assert payload["base_keyword"] == "openai"


def test_get_trend_task_summary_endpoint(client):
    from app.main import app

    app.dependency_overrides[get_trend_task_service] = lambda: FakeTrendTaskService()
    try:
        response = client.get("/api/trends/tasks/trend-task-123/summary")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["top_effective_keywords"][0]["keyword"] == "chatgpt api"


def test_export_trend_task_endpoint(client):
    from app.main import app

    app.dependency_overrides[get_trend_task_service] = lambda: FakeTrendTaskService()
    try:
        response = client.get("/api/trends/tasks/trend-task-123/export")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["task_id"] == "trend-task-123"
    assert payload["status"] == "completed"


def test_cancel_trend_task_endpoint(client):
    from app.main import app

    app.dependency_overrides[get_trend_task_service] = lambda: FakeTrendTaskService()
    try:
        response = client.post("/api/trends/tasks/trend-task-123/cancel")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "cancelled"


def test_retry_trend_task_endpoint(client):
    from app.main import app

    app.dependency_overrides[get_trend_task_service] = lambda: FakeTrendTaskService()
    try:
        response = client.post("/api/trends/tasks/trend-task-123/retry")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "pending"
    assert payload["new_task_id"] == "trend-task-456"
