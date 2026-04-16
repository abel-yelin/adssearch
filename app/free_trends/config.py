from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class FreeTrendsConfig:
    timezone: str = "Asia/Shanghai"
    schedule_time: str = "09:00"
    geo: str = "US"
    time_range: str = "now 7-d"
    search_type: str = ""
    language: str = "en-US"
    batch_size: int = 5
    max_batches_per_run: int = 40
    max_depth: int = 2
    retry_limit: int = 3
    max_consecutive_failures: int = 5
    cooldown_hours: int = 24
    output_dir: str = "./free_trends_output"
    database_path: str = "./free_trends_output/free_trends.db"
    status_file: str = "./free_trends_output/service_status.json"
    log_file: str = "./free_trends_output/service.log"
    batch_delay_min_seconds: float = 3.0
    batch_delay_max_seconds: float = 8.0
    root_terms: list[str] = field(default_factory=list)
    browser_headless: bool = True
    browser_channel: str | None = "chrome"
    browser_executable_path: str | None = None
    browser_user_data_dir: str = "./free_trends_output/browser-profile"
    request_timeout_ms: int = 45000

    @property
    def schedule_hour(self) -> int:
        return int(self.schedule_time.split(":", 1)[0])

    @property
    def schedule_minute(self) -> int:
        return int(self.schedule_time.split(":", 1)[1])

    def ensure_paths(self) -> None:
        output_dir = Path(self.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        Path(self.browser_user_data_dir).mkdir(parents=True, exist_ok=True)
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.status_file).parent.mkdir(parents=True, exist_ok=True)
        Path(self.log_file).parent.mkdir(parents=True, exist_ok=True)


def load_config(path: str | Path) -> FreeTrendsConfig:
    raw_path = Path(path)
    payload = json.loads(raw_path.read_text(encoding="utf-8"))
    config = FreeTrendsConfig(**payload)
    config.ensure_paths()
    return config
