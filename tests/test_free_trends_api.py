from app.dependencies.services import get_free_trends_service
from app.schemas.free_trends import (
    FreeTrendsRunResultsResponse,
    FreeTrendsRunSummaryResponse,
    FreeTrendsSeedsListResponse,
    FreeTrendsSeedsResponse,
    FreeTrendsStatusResponse,
)
from app.schemas.free_trends_requests import FreeTrendsRunRequestResponse


class FakeFreeTrendsService:
    def _seed_item(self, seed_id, term, group_key="general", enabled=True, priority=100, tags=None, notes=None):
        return {
            "id": seed_id,
            "term": term,
            "normalized_term": term.lower(),
            "group_key": group_key,
            "enabled": enabled,
            "priority": priority,
            "tags": tags or [],
            "notes": notes,
            "cooldown_until": None,
            "last_scanned_at": None,
            "last_status": None,
            "created_at": "2026-04-16T00:00:00Z",
            "updated_at": "2026-04-16T00:00:00Z",
        }

    def get_status(self):
        return FreeTrendsStatusResponse(
            config_path="/tmp/free_trends.json",
            schedule_time="09:00",
            timezone="Asia/Shanghai",
            latest_run={
                "run_id": "run-1",
                "status": "completed",
                "started_at": "2026-04-16T00:00:00Z",
                "finished_at": "2026-04-16T00:01:00Z",
                "new_keyword_count": 5,
                "output_paths": {
                    "json": "/tmp/a.json",
                    "csv": "/tmp/a.csv",
                    "latest_csv": "/tmp/latest.csv",
                },
                "blocked_message": None,
                "error_message": None,
            },
        )

    def list_seeds(self, **kwargs):
        return FreeTrendsSeedsListResponse(
            items=[self._seed_item(1, "image", group_key="media", tags=["media"])],
            total=1,
            page=kwargs.get("page", 1),
            page_size=kwargs.get("page_size", 50),
            search=kwargs.get("search"),
            group_key=kwargs.get("group_key"),
            enabled=kwargs.get("enabled"),
            sort_by=kwargs.get("sort_by", "priority"),
            sort_order=kwargs.get("sort_order", "desc"),
        )

    def replace_seeds(self, terms):
        return FreeTrendsSeedsResponse(
            items=[self._seed_item(index + 1, term) for index, term in enumerate(terms)]
        )

    def create_seed(self, request):
        return self._seed_item(2, request.term, request.group_key, request.enabled, request.priority, request.tags, request.notes)

    def update_seed(self, seed_id, request):
        return self._seed_item(seed_id, request.term, request.group_key, request.enabled, request.priority, request.tags, request.notes)

    def delete_seed(self, seed_id):
        return {"deleted": True, "seed_id": seed_id}

    def bulk_replace_seed_items(self, items):
        return FreeTrendsSeedsResponse(
            items=[
                self._seed_item(index + 1, item.term, item.group_key, item.enabled, item.priority, item.tags, item.notes)
                for index, item in enumerate(items)
            ]
        )

    def get_latest_run(self):
        return FreeTrendsRunSummaryResponse(
            run_id="run-1",
            status="completed",
            started_at="2026-04-16T00:00:00Z",
            finished_at="2026-04-16T00:01:00Z",
            new_keyword_count=5,
            output_paths={"json": "/tmp/a.json", "csv": "/tmp/a.csv", "latest_csv": "/tmp/latest.csv"},
            blocked_message=None,
            error_message=None,
        )

    def get_run(self, run_id):
        return FreeTrendsRunSummaryResponse(
            run_id=run_id,
            status="completed",
            started_at="2026-04-16T00:00:00Z",
            finished_at="2026-04-16T00:01:00Z",
            new_keyword_count=5,
            output_paths={"json": "/tmp/a.json", "csv": "/tmp/a.csv", "latest_csv": "/tmp/latest.csv"},
            blocked_message=None,
            error_message=None,
        )

    def get_run_results(self, run_id):
        return FreeTrendsRunResultsResponse(
            run_id=run_id,
            items=[
                {
                    "run_id": run_id,
                    "normalized_term": "trump jesus ai",
                    "term": "trump jesus ai",
                    "source_term": "ai",
                    "source_terms": ["ai"],
                    "depth": 1,
                    "discovered_at": "2026-04-16T00:00:00Z",
                    "batch_id": "batch-1",
                    "region": "US",
                    "time_range": "now 7-d",
                    "trend_type": "rising",
                    "value_label": "Breakout",
                }
            ],
        )

    def create_run_request(self):
        return FreeTrendsRunRequestResponse(
            request_id="req-1",
            status="pending",
            requested_at="2026-04-16T00:02:00Z",
            started_at=None,
            finished_at=None,
            run_id=None,
            error_message=None,
        )

    def get_run_request(self, request_id):
        return FreeTrendsRunRequestResponse(
            request_id=request_id,
            status="completed",
            requested_at="2026-04-16T00:02:00Z",
            started_at="2026-04-16T00:02:10Z",
            finished_at="2026-04-16T00:03:00Z",
            run_id="run-2",
            error_message=None,
        )


def test_free_trends_status_endpoint(client):
    from app.main import app

    app.dependency_overrides[get_free_trends_service] = lambda: FakeFreeTrendsService()
    try:
        response = client.get("/api/free-trends/status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["latest_run"]["run_id"] == "run-1"


def test_free_trends_seeds_endpoints(client):
    from app.main import app

    app.dependency_overrides[get_free_trends_service] = lambda: FakeFreeTrendsService()
    try:
        list_response = client.get("/api/free-trends/seeds?search=ima&group_key=media&enabled=true&page=1&page_size=20&sort_by=priority&sort_order=desc")
        replace_response = client.put("/api/free-trends/seeds", json={"root_terms": ["image", "ai"]})
        create_response = client.post(
            "/api/free-trends/seeds",
            json={"term": "guide", "group_key": "tool_actions", "enabled": True, "priority": 80, "tags": ["tool"]},
        )
        update_response = client.put(
            "/api/free-trends/seeds/2",
            json={"term": "guide ai", "group_key": "tool_actions", "enabled": True, "priority": 90, "tags": ["tool", "ai"]},
        )
        delete_response = client.delete("/api/free-trends/seeds/2")
        bulk_replace_response = client.post(
            "/api/free-trends/seeds/bulk-replace",
            json={
                "items": [
                    {"term": "image", "group_key": "media", "enabled": True, "priority": 100, "tags": ["media"]},
                    {"term": "ai", "group_key": "ai", "enabled": True, "priority": 200, "tags": ["ai"]},
                ]
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
    assert list_response.json()["group_key"] == "media"
    assert list_response.json()["items"][0]["id"] == 1
    assert list_response.json()["items"][0]["term"] == "image"
    assert replace_response.status_code == 200
    assert len(replace_response.json()["items"]) == 2
    assert create_response.status_code == 201
    assert create_response.json()["group_key"] == "tool_actions"
    assert update_response.status_code == 200
    assert update_response.json()["term"] == "guide ai"
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True
    assert bulk_replace_response.status_code == 200
    assert bulk_replace_response.json()["items"][1]["priority"] == 200


def test_free_trends_run_endpoints(client):
    from app.main import app

    app.dependency_overrides[get_free_trends_service] = lambda: FakeFreeTrendsService()
    try:
        latest_response = client.get("/api/free-trends/runs/latest")
        run_response = client.get("/api/free-trends/runs/run-1")
        results_response = client.get("/api/free-trends/runs/run-1/results")
        trigger_response = client.post("/api/free-trends/runs")
        request_response = client.get("/api/free-trends/run-requests/req-1")
    finally:
        app.dependency_overrides.clear()

    assert latest_response.status_code == 200
    assert run_response.status_code == 200
    assert results_response.status_code == 200
    assert results_response.json()["items"][0]["value_label"] == "Breakout"
    assert trigger_response.status_code == 202
    assert trigger_response.json()["request_id"] == "req-1"
    assert request_response.status_code == 200
    assert request_response.json()["run_id"] == "run-2"
