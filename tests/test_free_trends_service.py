import asyncio
import csv
import json
from datetime import UTC, datetime
from pathlib import Path

from app.free_trends.collector import BatchCapture, RisingQuery, TrendsBlockedError
from app.free_trends.config import FreeTrendsConfig, load_config
from app.free_trends.normalize import canonical_term, normalize_term
from app.free_trends.scheduler import build_scheduler
from app.free_trends.service import DailyTrendsDiscoveryService, QueueItem
from app.free_trends.storage import FreeTrendsStorage


class FakeCollector:
    def __init__(self, scripted_batches):
        self.scripted_batches = scripted_batches
        self.calls = []
        self.started = False
        self.closed = False

    async def start(self):
        self.started = True

    async def close(self):
        self.closed = True

    async def collect_batch(self, *, keywords, time_range, geo):
        self.calls.append({"keywords": keywords, "time_range": time_range, "geo": geo})
        result = self.scripted_batches[len(self.calls) - 1]
        if isinstance(result, Exception):
            raise result
        return result


def _build_config(tmp_path: Path, root_terms: list[str]) -> FreeTrendsConfig:
    output_dir = tmp_path / "output"
    return FreeTrendsConfig(
        output_dir=str(output_dir),
        database_path=str(output_dir / "free_trends.db"),
        status_file=str(output_dir / "status.json"),
        log_file=str(output_dir / "service.log"),
        browser_user_data_dir=str(output_dir / "browser"),
        root_terms=root_terms,
        batch_delay_min_seconds=0,
        batch_delay_max_seconds=0,
        max_batches_per_run=10,
        max_depth=0,
    )


def test_load_config_reads_expected_defaults(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "timezone": "Asia/Shanghai",
                "schedule_time": "09:00",
                "geo": "US",
                "time_range": "now 7-d",
                "batch_size": 5,
                "output_dir": str(tmp_path / "output"),
                "database_path": str(tmp_path / "output" / "db.sqlite3"),
                "status_file": str(tmp_path / "output" / "status.json"),
                "log_file": str(tmp_path / "output" / "service.log"),
                "browser_user_data_dir": str(tmp_path / "output" / "browser"),
                "root_terms": ["Guide", "Editor"],
            }
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.schedule_time == "09:00"
    assert config.geo == "US"
    assert config.batch_size == 5
    assert config.root_terms == ["Guide", "Editor"]
    assert Path(config.output_dir).exists()


def test_term_normalization_handles_case_spaces_and_hidden_chars():
    assert normalize_term("  Voice   Generator\u200b ") == "Voice Generator"
    assert canonical_term("  Voice   Generator ") == "voice generator"


def test_batch_builder_keeps_groups_of_five(tmp_path):
    service = DailyTrendsDiscoveryService(
        _build_config(tmp_path, []),
        FreeTrendsStorage(str(tmp_path / "db.sqlite3")),
        FakeCollector([]),
        sleep_fn=lambda _: None,
    )
    queue = [
        QueueItem("a", 0, "a"),
        QueueItem("b", 0, "b"),
        QueueItem("c", 0, "c"),
        QueueItem("d", 0, "d"),
        QueueItem("e", 0, "e"),
        QueueItem("f", 0, "f"),
    ]
    from collections import deque

    batch = service._next_batch(deque(queue))
    assert [item.term for item in batch] == ["a", "b", "c", "d", "e"]


def test_rising_parser_prefers_rising_ranked_list():
    payload = {
        "default": {
            "rankedList": [
                {"rankedKeyword": [{"query": "old", "value": 88}]},
                {"rankedKeyword": [{"query": "new tool", "value": "Breakout"}]},
            ]
        }
    }
    from app.free_trends.collector import FreeTrendsCollector

    rising = FreeTrendsCollector._extract_rising_queries(payload)
    assert len(rising) == 1
    assert rising[0].query == "new tool"
    assert rising[0].value_label == "Breakout"


def test_dom_related_queries_parser_supports_chinese_new_explore_layout():
    from app.free_trends.collector import FreeTrendsCollector

    body_text = """
    image
    相关查询
    分析
    搜索量上升
    1
    on url change handler
    在 url 更改处理程序上
    飙升
    2
    on url change core handler executed
    url 更改时执行核心处理程序
    飙升
    3
    url starter crossword
    网址起始填字游戏
    +4,100%
    4
    summary of a sports game
    一场体育比赛的总结
    +4,050%
    当前显示的是第 1-5 个查询（共 16 个）
    """

    parsed = FreeTrendsCollector._parse_dom_related_queries(body_text, ["image"])

    assert "image" in parsed
    assert [item.query for item in parsed["image"]] == [
        "on url change handler",
        "on url change core handler executed",
        "url starter crossword",
        "summary of a sports game",
    ]
    assert [item.value_label for item in parsed["image"]] == ["飙升", "飙升", "+4,100%", "+4,050%"]


def test_dedup_preserves_multiple_sources(tmp_path):
    config = _build_config(tmp_path, ["guide", "editor"])
    storage = FreeTrendsStorage(config.database_path)
    collector = FakeCollector(
        [
            BatchCapture(
                rising_by_term={
                    "guide": [RisingQuery(query="voice generator", value_label="Breakout")],
                    "editor": [RisingQuery(query="voice generator", value_label="120%")],
                }
            )
        ]
    )
    service = DailyTrendsDiscoveryService(config, storage, collector, sleep_fn=lambda _: None)

    asyncio.run(service.run_once())

    latest = storage.get_latest_run_summary()
    items = storage.list_discovered_terms_for_run(latest["run_id"])
    assert len(items) == 1
    assert sorted(items[0]["source_terms"]) == ["editor", "guide"]


def test_recursive_queue_pushes_new_terms_until_max_depth(tmp_path):
    config = _build_config(tmp_path, ["guide", "editor", "creator", "maker", "downloader"])
    config.max_batches_per_run = 3
    config.max_depth = 2
    storage = FreeTrendsStorage(config.database_path)
    collector = FakeCollector(
        [
            BatchCapture(
                rising_by_term={
                    "guide": [RisingQuery(query="voice generator", value_label="Breakout")],
                    "editor": [],
                    "creator": [],
                    "maker": [],
                    "downloader": [],
                }
            ),
            BatchCapture(
                rising_by_term={
                    "voice generator": [RisingQuery(query="voice generator ai", value_label="250%")],
                }
            ),
            BatchCapture(
                rising_by_term={
                    "voice generator ai": [],
                }
            ),
        ]
    )
    service = DailyTrendsDiscoveryService(config, storage, collector, sleep_fn=lambda _: None)

    summary = asyncio.run(service.run_once())

    assert summary["new_keyword_count"] == 2
    assert collector.calls[1]["keywords"] == ["voice generator"]
    assert collector.calls[2]["keywords"] == ["voice generator ai"]


def test_scheduler_uses_0900_asia_shanghai(tmp_path):
    config = _build_config(tmp_path, ["guide"])
    scheduler = build_scheduler(config, lambda: None)
    job = scheduler.get_job("free-trends-daily-run")

    assert job is not None
    assert str(job.trigger.timezone) == "Asia/Shanghai"
    assert job.trigger.fields[5].expressions[0].first == 9
    assert job.trigger.fields[6].expressions[0].first == 0


def test_outputs_write_json_csv_and_latest_csv(tmp_path):
    config = _build_config(tmp_path, ["guide", "editor", "creator", "maker", "downloader"])
    storage = FreeTrendsStorage(config.database_path)
    collector = FakeCollector(
        [
            BatchCapture(
                rising_by_term={
                    "guide": [RisingQuery(query="voice generator", value_label="Breakout")],
                    "editor": [],
                    "creator": [],
                    "maker": [],
                    "downloader": [],
                }
            )
        ]
    )
    service = DailyTrendsDiscoveryService(config, storage, collector, sleep_fn=lambda _: None)

    summary = asyncio.run(service.run_once())

    json_path = Path(summary["output_paths"]["json"])
    csv_path = Path(summary["output_paths"]["csv"])
    latest_path = Path(summary["output_paths"]["latest_csv"])
    assert json_path.exists()
    assert csv_path.exists()
    assert latest_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["items"][0]["term"] == "voice generator"
    with csv_path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["trend_type"] == "rising"


def test_blocked_batch_triggers_cooldown_and_finishes_run(tmp_path):
    config = _build_config(tmp_path, ["guide", "editor", "creator", "maker", "downloader"])
    storage = FreeTrendsStorage(config.database_path)
    collector = FakeCollector([TrendsBlockedError("blocked by google")])
    service = DailyTrendsDiscoveryService(config, storage, collector, sleep_fn=lambda _: None)

    summary = asyncio.run(service.run_once())

    assert summary["status"] == "blocked"
    rows = storage.list_available_seed_terms(datetime.now(UTC))
    assert rows == []


def test_smoke_run_with_ten_terms_produces_discovery_file(tmp_path):
    config = _build_config(
        tmp_path,
        ["guide", "editor", "creator", "maker", "downloader", "scraper", "detector", "checker", "generator", "calculator"],
    )
    collector = FakeCollector(
        [
            BatchCapture(
                rising_by_term={
                    "guide": [RisingQuery(query="voice generator", value_label="Breakout")],
                    "editor": [],
                    "creator": [],
                    "maker": [],
                    "downloader": [],
                }
            ),
            BatchCapture(
                rising_by_term={
                    "scraper": [RisingQuery(query="reddit scraper", value_label="230%")],
                    "detector": [],
                    "checker": [],
                    "generator": [],
                    "calculator": [],
                }
            ),
            BatchCapture(rising_by_term={"voice generator": [], "reddit scraper": []}),
        ]
    )
    storage = FreeTrendsStorage(config.database_path)
    service = DailyTrendsDiscoveryService(config, storage, collector, sleep_fn=lambda _: None)

    summary = asyncio.run(service.run_once())

    assert summary["new_keyword_count"] == 2
    latest_csv = Path(summary["output_paths"]["latest_csv"])
    assert latest_csv.exists()
