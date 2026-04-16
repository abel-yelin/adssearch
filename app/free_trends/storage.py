from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.free_trends.normalize import canonical_term, normalize_term


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class SeedTermRow:
    term: str
    normalized_term: str
    cooldown_until: str | None
    last_scanned_at: str | None
    last_status: str | None


class FreeTrendsStorage:
    def __init__(self, database_path: str):
        self.database_path = database_path
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS seed_terms (
                    normalized_term TEXT PRIMARY KEY,
                    term TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    cooldown_until TEXT NULL,
                    last_scanned_at TEXT NULL,
                    last_status TEXT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NULL,
                    status TEXT NOT NULL,
                    new_keyword_count INTEGER NOT NULL DEFAULT 0,
                    output_json_path TEXT NULL,
                    output_csv_path TEXT NULL,
                    latest_csv_path TEXT NULL,
                    error_message TEXT NULL
                );

                CREATE TABLE IF NOT EXISTS run_batches (
                    batch_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    batch_no INTEGER NOT NULL,
                    keywords_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    new_discoveries_count INTEGER NOT NULL DEFAULT 0,
                    error_type TEXT NULL,
                    error_message TEXT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NULL
                );

                CREATE TABLE IF NOT EXISTS discovered_terms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    normalized_term TEXT NOT NULL,
                    term TEXT NOT NULL,
                    source_term TEXT NOT NULL,
                    source_terms_json TEXT NOT NULL,
                    depth INTEGER NOT NULL,
                    discovered_at TEXT NOT NULL,
                    batch_id TEXT NOT NULL,
                    region TEXT NOT NULL,
                    time_range TEXT NOT NULL,
                    trend_type TEXT NOT NULL,
                    value_label TEXT NOT NULL,
                    UNIQUE (run_id, normalized_term)
                );
                """
            )

    def upsert_seed_terms(self, terms: list[str]) -> None:
        now = utcnow().isoformat()
        rows = []
        for term in terms:
            normalized = canonical_term(term)
            cleaned = normalize_term(term)
            if not cleaned:
                continue
            rows.append((normalized, cleaned, now, now))
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO seed_terms (normalized_term, term, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(normalized_term) DO UPDATE SET
                  term = excluded.term,
                  updated_at = excluded.updated_at
                """,
                rows,
            )

    def list_available_seed_terms(self, now: datetime) -> list[SeedTermRow]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT term, normalized_term, cooldown_until, last_scanned_at, last_status
                FROM seed_terms
                WHERE enabled = 1
                  AND (cooldown_until IS NULL OR cooldown_until <= ?)
                ORDER BY COALESCE(last_scanned_at, ''), term
                """,
                (now.isoformat(),),
            ).fetchall()
        return [
            SeedTermRow(
                term=row["term"],
                normalized_term=row["normalized_term"],
                cooldown_until=row["cooldown_until"],
                last_scanned_at=row["last_scanned_at"],
                last_status=row["last_status"],
            )
            for row in rows
        ]

    def mark_seed_scanned(self, term: str, status: str, now: datetime) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE seed_terms
                SET last_scanned_at = ?, last_status = ?, updated_at = ?
                WHERE normalized_term = ?
                """,
                (now.isoformat(), status, now.isoformat(), canonical_term(term)),
            )

    def cool_down_seed_terms(self, terms: list[str], cooldown_hours: int, now: datetime, status: str) -> None:
        cooldown_until = (now + timedelta(hours=cooldown_hours)).isoformat()
        with self._connect() as conn:
            conn.executemany(
                """
                UPDATE seed_terms
                SET cooldown_until = ?, last_status = ?, updated_at = ?
                WHERE normalized_term = ?
                """,
                [
                    (cooldown_until, status, now.isoformat(), canonical_term(term))
                    for term in terms
                ],
            )

    def create_run(self, run_id: str, started_at: datetime) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runs (run_id, started_at, status)
                VALUES (?, ?, ?)
                """,
                (run_id, started_at.isoformat(), "running"),
            )

    def finish_run(
        self,
        run_id: str,
        *,
        finished_at: datetime,
        status: str,
        new_keyword_count: int,
        output_json_path: str,
        output_csv_path: str,
        latest_csv_path: str,
        error_message: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE runs
                SET finished_at = ?, status = ?, new_keyword_count = ?, output_json_path = ?,
                    output_csv_path = ?, latest_csv_path = ?, error_message = ?
                WHERE run_id = ?
                """,
                (
                    finished_at.isoformat(),
                    status,
                    new_keyword_count,
                    output_json_path,
                    output_csv_path,
                    latest_csv_path,
                    error_message,
                    run_id,
                ),
            )

    def create_batch(self, batch_id: str, run_id: str, batch_no: int, keywords: list[str], started_at: datetime) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO run_batches (batch_id, run_id, batch_no, keywords_json, status, started_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (batch_id, run_id, batch_no, json.dumps(keywords, ensure_ascii=False), "running", started_at.isoformat()),
            )

    def finish_batch(
        self,
        batch_id: str,
        *,
        status: str,
        finished_at: datetime,
        retry_count: int,
        new_discoveries_count: int,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE run_batches
                SET status = ?, finished_at = ?, retry_count = ?, new_discoveries_count = ?,
                    error_type = ?, error_message = ?
                WHERE batch_id = ?
                """,
                (
                    status,
                    finished_at.isoformat(),
                    retry_count,
                    new_discoveries_count,
                    error_type,
                    error_message,
                    batch_id,
                ),
            )

    def upsert_discovered_term(
        self,
        *,
        run_id: str,
        term: str,
        source_term: str,
        depth: int,
        discovered_at: datetime,
        batch_id: str,
        region: str,
        time_range: str,
        trend_type: str,
        value_label: str,
    ) -> bool:
        normalized = canonical_term(term)
        cleaned = normalize_term(term)
        source_cleaned = normalize_term(source_term)
        with self._connect() as conn:
            existing = conn.execute(
                """
                SELECT id, source_terms_json
                FROM discovered_terms
                WHERE run_id = ? AND normalized_term = ?
                """,
                (run_id, normalized),
            ).fetchone()
            if existing is not None:
                existing_sources = json.loads(existing["source_terms_json"])
                if source_cleaned not in existing_sources:
                    existing_sources.append(source_cleaned)
                    conn.execute(
                        """
                        UPDATE discovered_terms
                        SET source_terms_json = ?
                        WHERE id = ?
                        """,
                        (json.dumps(existing_sources, ensure_ascii=False), existing["id"]),
                    )
                return False

            conn.execute(
                """
                INSERT INTO discovered_terms (
                    run_id, normalized_term, term, source_term, source_terms_json,
                    depth, discovered_at, batch_id, region, time_range, trend_type, value_label
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    normalized,
                    cleaned,
                    source_cleaned,
                    json.dumps([source_cleaned], ensure_ascii=False),
                    depth,
                    discovered_at.isoformat(),
                    batch_id,
                    region,
                    time_range,
                    trend_type,
                    value_label,
                ),
            )
            return True

    def list_discovered_terms_for_run(self, run_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT run_id, normalized_term, term, source_term, source_terms_json, depth,
                       discovered_at, batch_id, region, time_range, trend_type, value_label
                FROM discovered_terms
                WHERE run_id = ?
                ORDER BY discovered_at ASC, term ASC
                """,
                (run_id,),
            ).fetchall()
        results = []
        for row in rows:
            results.append(
                {
                    "run_id": row["run_id"],
                    "normalized_term": row["normalized_term"],
                    "term": row["term"],
                    "source_term": row["source_term"],
                    "source_terms": json.loads(row["source_terms_json"]),
                    "depth": row["depth"],
                    "discovered_at": row["discovered_at"],
                    "batch_id": row["batch_id"],
                    "region": row["region"],
                    "time_range": row["time_range"],
                    "trend_type": row["trend_type"],
                    "value_label": row["value_label"],
                }
            )
        return results

    def get_latest_run_summary(self) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT run_id, started_at, finished_at, status, new_keyword_count,
                       output_json_path, output_csv_path, latest_csv_path, error_message
                FROM runs
                ORDER BY started_at DESC
                LIMIT 1
                """
            ).fetchone()
        return dict(row) if row else None
