from app.dependencies.services import get_trend_discovery_service
from app.schemas.trend_discovery import TrendDiscoveryResponse


class FakeTrendDiscoveryService:
    def discover(self, request):
        return TrendDiscoveryResponse(
            keyword_count=6,
            scanned_keyword_count=6,
            batch_count=2,
            batch_size=5,
            time_range="today 3-m",
            geo="US",
            risers=[
                {
                    "keyword": "voice generator",
                    "signal": "surging",
                    "batch_no": 1,
                    "latest_value": 31,
                    "recent_avg": 22.5,
                    "baseline_avg": 9.2,
                    "absolute_gain": 13.3,
                    "growth_ratio": 2.44,
                    "slope": 4.0,
                    "score": 108.7,
                }
            ],
            batches=[
                {
                    "batch_no": 1,
                    "keywords": ["voice", "audio", "studio", "music", "video"],
                    "data_points": 12,
                    "returned_keywords": ["voice", "audio", "studio", "music", "video"],
                },
                {
                    "batch_no": 2,
                    "keywords": ["generator"],
                    "data_points": 12,
                    "returned_keywords": ["generator"],
                },
            ],
            notes=["Free scan mode uses Google Trends-compatible batches of up to 5 keywords."],
        )


def test_trend_root_discovery_endpoint(client):
    from app.main import app

    app.dependency_overrides[get_trend_discovery_service] = lambda: FakeTrendDiscoveryService()
    try:
        response = client.post(
            "/api/trends/root-discovery",
            json={
                "keyword_blob": "voice,audio,studio,music,video,generator",
                "time_range": "today 3-m",
                "geo": "US",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["keyword_count"] == 6
    assert payload["batch_count"] == 2
    assert payload["risers"][0]["keyword"] == "voice generator"
