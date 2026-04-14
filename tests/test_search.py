from app.dependencies.services import get_ads_task_service
from app.schemas.search import SearchTaskStatusResponse, SearchTaskSubmitResponse, TaskActionResponse


class FakeTaskService:
    def submit_search(self, request):
        return SearchTaskSubmitResponse(
            success=True,
            task_id="task-1234",
            status="queued",
            message="Search task submitted successfully.",
        )

    def get_task_status(self, task_id):
        return SearchTaskStatusResponse(
            success=True,
            task_id=task_id,
            status="finished",
            result={
                "success": True,
                "task_id": "worker-1234",
                "data": {
                    "query_domain": "example.com",
                    "has_ads": True,
                    "advertisers": [],
                    "all_domains": ["example.com", "other-site.com"],
                    "other_domains": ["other-site.com"],
                    "ad_creatives": [],
                    "total_ads_found": 1,
                },
                "duration_seconds": 0.12,
            },
            retries_left=1,
        )

    def cancel_task(self, task_id):
        return TaskActionResponse(
            success=True,
            task_id=task_id,
            status="canceled",
            message="Task canceled successfully.",
        )

    def retry_task(self, task_id):
        return TaskActionResponse(
            success=True,
            task_id=task_id,
            new_task_id="task-5678",
            status="queued",
            message="Task retried successfully.",
        )


def test_search_endpoint(client):
    from app.main import app

    app.dependency_overrides[get_ads_task_service] = lambda: FakeTaskService()
    try:
        response = client.post(
            "/api/search",
            json={
                "domain": "example.com",
                "region": "US",
                "max_scroll_pages": 3,
                "timeout": 10000,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    payload = response.json()
    assert payload["success"] is True
    assert payload["task_id"] == "task-1234"
    assert payload["status"] == "queued"


def test_task_status_endpoint(client):
    from app.main import app

    app.dependency_overrides[get_ads_task_service] = lambda: FakeTaskService()
    try:
        response = client.get("/api/tasks/task-1234")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["task_id"] == "task-1234"
    assert payload["status"] == "finished"
    assert payload["result"]["data"]["query_domain"] == "example.com"
    assert payload["retries_left"] == 1


def test_cancel_task_endpoint(client):
    from app.main import app

    app.dependency_overrides[get_ads_task_service] = lambda: FakeTaskService()
    try:
        response = client.post("/api/tasks/task-1234/cancel")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["status"] == "canceled"


def test_retry_task_endpoint(client):
    from app.main import app

    app.dependency_overrides[get_ads_task_service] = lambda: FakeTaskService()
    try:
        response = client.post("/api/tasks/task-1234/retry")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["status"] == "queued"
    assert payload["new_task_id"] == "task-5678"
