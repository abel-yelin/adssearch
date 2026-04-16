from __future__ import annotations

import csv
import json
import logging
import random
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.free_trends.collector import (
    BatchCapture,
    FreeTrendsCollector,
    RisingQuery,
    TrendsBlockedError,
    TrendsCollectionError,
)
from app.free_trends.config import FreeTrendsConfig
from app.free_trends.normalize import canonical_term, normalize_term
from app.free_trends.storage import FreeTrendsStorage, utcnow


@dataclass(slots=True)
class QueueItem:
    term: str
    depth: int
    source_term: str


class DailyTrendsDiscoveryService:
    def __init__(
        self,
        config: FreeTrendsConfig,
        storage: FreeTrendsStorage,
        collector: FreeTrendsCollector,
        *,
        logger: logging.Logger | None = None,
        sleep_fn=time.sleep,
    ):
        self.config = config
        self.storage = storage
        self.collector = collector
        self.logger = logger or logging.getLogger(__name__)
        self.sleep_fn = sleep_fn

    async def run_once(self) -> dict:
        return await self._run_once_internal(request_id=None)

    async def run_once_for_request(self, request_id: str) -> dict:
        return await self._run_once_internal(request_id=request_id)

    async def _run_once_internal(self, request_id: str | None) -> dict:
        self.storage.upsert_seed_terms(self.config.root_terms)
        start_time = utcnow()
        run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
        self.storage.create_run(run_id, start_time)
        self.logger.info("daily trends run started run_id=%s", run_id)

        queue = deque(
            QueueItem(term=row.term, depth=0, source_term=row.term)
            for row in self.storage.list_available_seed_terms(start_time)
        )
        seen_terms = {canonical_term(item.term) for item in queue}
        consecutive_failures = 0
        batch_no = 0
        blocked = False
        blocked_message: str | None = None

        while queue and batch_no < self.config.max_batches_per_run:
            batch_items = self._next_batch(queue)
            if not batch_items:
                break
            batch_no += 1
            batch_id = f"{run_id}-batch-{batch_no:03d}"
            keywords = [item.term for item in batch_items]
            self.storage.create_batch(batch_id, run_id, batch_no, keywords, utcnow())
            self.logger.info("batch started run_id=%s batch_no=%s keywords=%s", run_id, batch_no, keywords)

            capture: BatchCapture | None = None
            error_type: str | None = None
            error_message: str | None = None
            for retry in range(1, self.config.retry_limit + 1):
                try:
                    capture = await self.collector.collect_batch(
                        keywords=keywords,
                        time_range=self.config.time_range,
                        geo=self.config.geo,
                    )
                    consecutive_failures = 0
                    break
                except TrendsBlockedError as exc:
                    blocked = True
                    error_type = "blocked"
                    error_message = str(exc)
                    self.storage.cool_down_seed_terms(
                        keywords,
                        cooldown_hours=self.config.cooldown_hours,
                        now=utcnow(),
                        status="blocked",
                    )
                    blocked_message = error_message
                    self.logger.warning("batch blocked run_id=%s batch_no=%s error=%s", run_id, batch_no, error_message)
                    break
                except TrendsCollectionError as exc:
                    consecutive_failures += 1
                    error_type = "collection_error"
                    error_message = str(exc)
                    self.logger.warning(
                        "batch retry run_id=%s batch_no=%s retry=%s error=%s",
                        run_id,
                        batch_no,
                        retry,
                        error_message,
                    )
                    if retry < self.config.retry_limit:
                        self.sleep_fn(2**retry)

            if capture is None:
                self.storage.finish_batch(
                    batch_id,
                    status="blocked" if blocked else "failed",
                    finished_at=utcnow(),
                    retry_count=self.config.retry_limit if not blocked else 1,
                    new_discoveries_count=0,
                    error_type=error_type,
                    error_message=error_message,
                )
                if blocked or consecutive_failures >= self.config.max_consecutive_failures:
                    break
                continue

            new_discoveries = self._persist_batch_results(
                run_id=run_id,
                batch_id=batch_id,
                batch_items=batch_items,
                capture=capture,
                seen_terms=seen_terms,
                queue=queue,
            )
            self.storage.finish_batch(
                batch_id,
                status="succeeded",
                finished_at=utcnow(),
                retry_count=0,
                new_discoveries_count=new_discoveries,
            )
            self.logger.info(
                "batch finished run_id=%s batch_no=%s new_discoveries=%s",
                run_id,
                batch_no,
                new_discoveries,
            )
            for item in batch_items:
                self.storage.mark_seed_scanned(item.term, "scanned", utcnow())

            if queue and batch_no < self.config.max_batches_per_run:
                delay = random.uniform(self.config.batch_delay_min_seconds, self.config.batch_delay_max_seconds)
                self.sleep_fn(delay)

        discovered = self.storage.list_discovered_terms_for_run(run_id)
        output_paths = self._write_outputs(run_id, discovered)
        finished_status = "blocked" if blocked else "completed"
        self.storage.finish_run(
            run_id,
            finished_at=utcnow(),
            status=finished_status,
            new_keyword_count=len(discovered),
            output_json_path=output_paths["json"],
            output_csv_path=output_paths["csv"],
            latest_csv_path=output_paths["latest_csv"],
            error_message=blocked_message,
        )
        summary = {
            "run_id": run_id,
            "status": finished_status,
            "started_at": start_time.isoformat(),
            "finished_at": utcnow().isoformat(),
            "new_keyword_count": len(discovered),
            "output_paths": output_paths,
            "blocked_message": blocked_message,
        }
        if request_id is not None:
            self.storage.finish_run_request(
                request_id,
                status="completed" if finished_status == "completed" else finished_status,
                finished_at=utcnow(),
                run_id=run_id,
                error_message=blocked_message,
            )
        Path(self.config.status_file).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        self.logger.info("daily trends run finished run_id=%s status=%s discovered=%s", run_id, finished_status, len(discovered))
        return summary

    def _next_batch(self, queue: deque[QueueItem]) -> list[QueueItem]:
        batch: list[QueueItem] = []
        while queue and len(batch) < self.config.batch_size:
            batch.append(queue.popleft())
        return batch

    def _persist_batch_results(
        self,
        *,
        run_id: str,
        batch_id: str,
        batch_items: list[QueueItem],
        capture: BatchCapture,
        seen_terms: set[str],
        queue: deque[QueueItem],
    ) -> int:
        new_discoveries = 0
        items_by_term = {item.term: item for item in batch_items}
        now = utcnow()
        for source_term, rising_items in capture.rising_by_term.items():
            for rising in rising_items:
                normalized_term = canonical_term(rising.query)
                cleaned_term = normalize_term(rising.query)
                if not cleaned_term:
                    continue
                inserted = self.storage.upsert_discovered_term(
                    run_id=run_id,
                    term=cleaned_term,
                    source_term=source_term,
                    depth=items_by_term.get(source_term, QueueItem(source_term, 0, source_term)).depth + 1,
                    discovered_at=now,
                    batch_id=batch_id,
                    region=self.config.geo,
                    time_range=self.config.time_range,
                    trend_type="rising",
                    value_label=rising.value_label,
                )
                if inserted:
                    new_discoveries += 1
                source_depth = items_by_term.get(source_term, QueueItem(source_term, 0, source_term)).depth
                if normalized_term not in seen_terms and source_depth + 1 <= self.config.max_depth:
                    queue.append(QueueItem(term=cleaned_term, depth=source_depth + 1, source_term=source_term))
                    seen_terms.add(normalized_term)
        return new_discoveries

    def _write_outputs(self, run_id: str, discovered: list[dict]) -> dict[str, str]:
        today_dir = Path(self.config.output_dir) / datetime.now().strftime("%Y-%m-%d")
        today_dir.mkdir(parents=True, exist_ok=True)
        json_path = today_dir / f"{run_id}.json"
        csv_path = today_dir / f"{run_id}.csv"
        latest_csv_path = Path(self.config.output_dir) / "latest_hot_keywords.csv"

        payload = {
            "run_id": run_id,
            "generated_at": utcnow().isoformat(),
            "geo": self.config.geo,
            "time_range": self.config.time_range,
            "trend_type": "rising",
            "items": discovered,
        }
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self._write_csv(csv_path, discovered)
        self._write_csv(latest_csv_path, discovered)
        return {
            "json": str(json_path),
            "csv": str(csv_path),
            "latest_csv": str(latest_csv_path),
        }

    @staticmethod
    def _write_csv(path: Path, discovered: list[dict]) -> None:
        fieldnames = [
            "term",
            "normalized_term",
            "source_term",
            "source_terms",
            "depth",
            "discovered_at",
            "batch_id",
            "region",
            "time_range",
            "trend_type",
            "value_label",
        ]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for item in discovered:
                filtered = {key: item.get(key) for key in fieldnames}
                writer.writerow(
                    {
                        **filtered,
                        "source_terms": "|".join(item["source_terms"]),
                    }
                )


def build_live_service(config: FreeTrendsConfig, *, logger: logging.Logger | None = None) -> DailyTrendsDiscoveryService:
    storage = FreeTrendsStorage(config.database_path)
    collector = FreeTrendsCollector(
        headless=config.browser_headless,
        browser_channel=config.browser_channel,
        browser_executable_path=config.browser_executable_path,
        browser_user_data_dir=config.browser_user_data_dir,
        language=config.language,
        timeout_ms=config.request_timeout_ms,
    )
    return DailyTrendsDiscoveryService(config, storage, collector, logger=logger)
