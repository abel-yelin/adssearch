from app.schemas.trend_discovery import TrendDiscoveryRequest
from app.services.trend_discovery_service import TrendDiscoveryService


class FakeTrendProvider:
    def __init__(self):
        self.calls = []

    def fetch_interest_over_time(self, *, keywords, time_range, geo, language, timezone_offset):
        self.calls.append(
            {
                "keywords": keywords,
                "time_range": time_range,
                "geo": geo,
                "language": language,
                "timezone_offset": timezone_offset,
            }
        )
        points = []
        keyword_values = {
            "guide": [3, 3, 4, 4, 5, 5, 8, 10, 16, 20, 24, 28],
            "editor": [5, 5, 5, 6, 5, 6, 6, 5, 6, 6, 7, 6],
            "creator": [1, 1, 1, 1, 2, 2, 3, 4, 10, 18, 24, 30],
            "maker": [2, 2, 3, 3, 2, 3, 3, 4, 4, 4, 5, 4],
            "downloader": [0, 0, 1, 0, 1, 1, 2, 2, 14, 18, 22, 25],
            "scraper": [3, 4, 3, 4, 4, 5, 4, 5, 6, 6, 6, 7],
        }
        for index in range(12):
            points.append(
                {
                    "timestamp": f"2026-01-{index + 1:02d}",
                    "values": {
                        keyword: keyword_values.get(keyword.casefold(), [0] * 12)[index]
                        for keyword in keywords
                    },
                }
            )
        return points


def test_discover_trend_risers_batches_keywords_and_scores_growth():
    provider = FakeTrendProvider()
    service = TrendDiscoveryService(provider=provider, sleep_fn=lambda _: None)

    response = service.discover(
        TrendDiscoveryRequest(
            keyword_blob="Guide,Editor,Creator,Maker,Downloader,Scraper,guide",
            time_range="today 3-m",
            batch_size=5,
            recent_window=4,
            baseline_window=8,
            min_growth_ratio=1.5,
            min_absolute_gain=5,
            min_recent_avg=5,
            top_n=10,
            batch_delay_seconds=0,
        )
    )

    assert response.keyword_count == 6
    assert response.batch_count == 2
    assert provider.calls[0]["keywords"] == ["Guide", "Editor", "Creator", "Maker", "Downloader"]
    assert provider.calls[1]["keywords"] == ["Scraper"]
    assert [item.keyword for item in response.risers] == ["Downloader", "Creator", "Guide"]
    assert response.risers[0].signal == "breakout"


def test_discover_trend_risers_returns_empty_when_thresholds_are_not_met():
    provider = FakeTrendProvider()
    service = TrendDiscoveryService(provider=provider, sleep_fn=lambda _: None)

    response = service.discover(
        TrendDiscoveryRequest(
            keywords=["editor", "maker", "scraper"],
            min_growth_ratio=3.0,
            min_absolute_gain=20,
            min_recent_avg=10,
            batch_delay_seconds=0,
        )
    )

    assert response.risers == []
    assert "No keywords crossed the configured growth thresholds in this scan." in response.notes
