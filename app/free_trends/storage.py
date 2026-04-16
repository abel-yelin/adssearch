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
    id: int
    term: str
    normalized_term: str
    group_key: str | None
    enabled: bool
    priority: int
    tags_json: str
    notes: str | None
    cooldown_until: str | None
    last_scanned_at: str | None
    last_status: str | None
    created_at: str
    updated_at: str


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
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    normalized_term TEXT NOT NULL UNIQUE,
                    term TEXT NOT NULL,
                    group_key TEXT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    priority INTEGER NOT NULL DEFAULT 100,
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    notes TEXT NULL,
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

                CREATE TABLE IF NOT EXISTS run_requests (
                    request_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    requested_at TEXT NOT NULL,
                    started_at TEXT NULL,
                    finished_at TEXT NULL,
                    run_id TEXT NULL,
                    error_message TEXT NULL
                );
                """
            )
            self._migrate_seed_terms(conn)

    @staticmethod
    def _migrate_seed_terms(conn: sqlite3.Connection) -> None:
        columns = {
            row["name"]: row
            for row in conn.execute("PRAGMA table_info(seed_terms)").fetchall()
        }
        required_columns = {
            "id": "ALTER TABLE seed_terms ADD COLUMN id INTEGER",
            "group_key": "ALTER TABLE seed_terms ADD COLUMN group_key TEXT NULL",
            "priority": "ALTER TABLE seed_terms ADD COLUMN priority INTEGER NOT NULL DEFAULT 100",
            "tags_json": "ALTER TABLE seed_terms ADD COLUMN tags_json TEXT NOT NULL DEFAULT '[]'",
            "notes": "ALTER TABLE seed_terms ADD COLUMN notes TEXT NULL",
        }
        for column_name, ddl in required_columns.items():
            if column_name not in columns:
                conn.execute(ddl)

    def upsert_seed_terms(self, terms: list[str]) -> None:
        now = utcnow().isoformat()
        rows = []
        for term in terms:
            normalized = canonical_term(term)
            cleaned = normalize_term(term)
            if not cleaned:
                continue
            rows.append((normalized, cleaned, "general", 100, "[]", None, now, now))
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO seed_terms (normalized_term, term, group_key, priority, tags_json, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(normalized_term) DO UPDATE SET
                  term = excluded.term,
                  group_key = COALESCE(seed_terms.group_key, excluded.group_key),
                  priority = COALESCE(seed_terms.priority, excluded.priority),
                  tags_json = COALESCE(seed_terms.tags_json, excluded.tags_json),
                  notes = COALESCE(seed_terms.notes, excluded.notes),
                  updated_at = excluded.updated_at
                """,
                rows,
            )

    def list_available_seed_terms(self, now: datetime) -> list[SeedTermRow]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, term, normalized_term, group_key, enabled, priority, tags_json, notes,
                       cooldown_until, last_scanned_at, last_status, created_at, updated_at
                FROM seed_terms
                WHERE enabled = 1
                  AND (cooldown_until IS NULL OR cooldown_until <= ?)
                ORDER BY priority DESC, COALESCE(last_scanned_at, ''), term
                """,
                (now.isoformat(),),
            ).fetchall()
        return [
            SeedTermRow(
                id=row["id"],
                term=row["term"],
                normalized_term=row["normalized_term"],
                group_key=row["group_key"],
                enabled=bool(row["enabled"]),
                priority=int(row["priority"] or 100),
                tags_json=row["tags_json"] or "[]",
                notes=row["notes"],
                cooldown_until=row["cooldown_until"],
                last_scanned_at=row["last_scanned_at"],
                last_status=row["last_status"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    def list_all_seed_terms(self) -> list[SeedTermRow]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, term, normalized_term, group_key, enabled, priority, tags_json, notes,
                       cooldown_until, last_scanned_at, last_status, created_at, updated_at
                FROM seed_terms
                ORDER BY priority DESC, term ASC
                """
            ).fetchall()
        return [
            SeedTermRow(
                id=row["id"],
                term=row["term"],
                normalized_term=row["normalized_term"],
                group_key=row["group_key"],
                enabled=bool(row["enabled"]),
                priority=int(row["priority"] or 100),
                tags_json=row["tags_json"] or "[]",
                notes=row["notes"],
                cooldown_until=row["cooldown_until"],
                last_scanned_at=row["last_scanned_at"],
                last_status=row["last_status"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    def query_seed_terms(
        self,
        *,
        search: str | None = None,
        group_key: str | None = None,
        enabled: bool | None = None,
        page: int = 1,
        page_size: int = 50,
        sort_by: str = "priority",
        sort_order: str = "desc",
    ) -> tuple[list[SeedTermRow], int]:
        where_clauses: list[str] = []
        params: list[object] = []

        if search:
            where_clauses.append("(term LIKE ? OR normalized_term LIKE ? OR IFNULL(notes, '') LIKE ?)")
            like = f"%{search.strip()}%"
            params.extend([like, like, like])
        if group_key:
            where_clauses.append("group_key = ?")
            params.append(group_key)
        if enabled is not None:
            where_clauses.append("enabled = ?")
            params.append(1 if enabled else 0)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        sort_column_map = {
            "priority": "priority",
            "term": "term",
            "updated_at": "updated_at",
            "created_at": "created_at",
            "last_scanned_at": "last_scanned_at",
        }
        resolved_sort = sort_column_map.get(sort_by, "priority")
        resolved_order = "ASC" if sort_order.lower() == "asc" else "DESC"
        limit = max(1, page_size)
        offset = max(0, (page - 1) * page_size)

        with self._connect() as conn:
            total = int(
                conn.execute(
                    f"SELECT COUNT(*) AS count FROM seed_terms {where_sql}",
                    params,
                ).fetchone()["count"]
            )
            rows = conn.execute(
                f"""
                SELECT id, term, normalized_term, group_key, enabled, priority, tags_json, notes,
                       cooldown_until, last_scanned_at, last_status, created_at, updated_at
                FROM seed_terms
                {where_sql}
                ORDER BY {resolved_sort} {resolved_order}, term ASC
                LIMIT ? OFFSET ?
                """,
                [*params, limit, offset],
            ).fetchall()

        return (
            [
                SeedTermRow(
                    id=row["id"],
                    term=row["term"],
                    normalized_term=row["normalized_term"],
                    group_key=row["group_key"],
                    enabled=bool(row["enabled"]),
                    priority=int(row["priority"] or 100),
                    tags_json=row["tags_json"] or "[]",
                    notes=row["notes"],
                    cooldown_until=row["cooldown_until"],
                    last_scanned_at=row["last_scanned_at"],
                    last_status=row["last_status"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
                for row in rows
            ],
            total,
        )

    def replace_seed_terms(self, terms: list[str]) -> None:
        now = utcnow().isoformat()
        rows = []
        for term in terms:
            normalized = canonical_term(term)
            cleaned = normalize_term(term)
            if not cleaned:
                continue
            rows.append((normalized, cleaned, "general", 100, "[]", None, now, now))
        with self._connect() as conn:
            conn.execute("DELETE FROM seed_terms")
            conn.executemany(
                """
                INSERT INTO seed_terms (normalized_term, term, group_key, priority, tags_json, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def create_seed_term(
        self,
        *,
        term: str,
        group_key: str | None,
        enabled: bool,
        priority: int,
        tags: list[str],
        notes: str | None,
    ) -> SeedTermRow:
        cleaned = normalize_term(term)
        if not cleaned:
            raise ValueError("Seed term cannot be empty.")
        normalized = canonical_term(cleaned)
        now = utcnow().isoformat()
        with self._connect() as conn:
            try:
                cursor = conn.execute(
                    """
                    INSERT INTO seed_terms (
                        normalized_term, term, group_key, enabled, priority, tags_json, notes, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        normalized,
                        cleaned,
                        group_key,
                        1 if enabled else 0,
                        priority,
                        json.dumps(tags, ensure_ascii=False),
                        notes,
                        now,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"Seed term '{cleaned}' already exists.") from exc
            row_id = cursor.lastrowid
        result = self.get_seed_term_by_id(int(row_id))
        assert result is not None
        return result

    def get_seed_term_by_id(self, seed_id: int) -> SeedTermRow | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, term, normalized_term, group_key, enabled, priority, tags_json, notes,
                       cooldown_until, last_scanned_at, last_status, created_at, updated_at
                FROM seed_terms
                WHERE id = ?
                """,
                (seed_id,),
            ).fetchone()
        if row is None:
            return None
        return SeedTermRow(
            id=row["id"],
            term=row["term"],
            normalized_term=row["normalized_term"],
            group_key=row["group_key"],
            enabled=bool(row["enabled"]),
            priority=int(row["priority"] or 100),
            tags_json=row["tags_json"] or "[]",
            notes=row["notes"],
            cooldown_until=row["cooldown_until"],
            last_scanned_at=row["last_scanned_at"],
            last_status=row["last_status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def update_seed_term(
        self,
        seed_id: int,
        *,
        term: str,
        group_key: str | None,
        enabled: bool,
        priority: int,
        tags: list[str],
        notes: str | None,
    ) -> SeedTermRow:
        cleaned = normalize_term(term)
        if not cleaned:
            raise ValueError("Seed term cannot be empty.")
        normalized = canonical_term(cleaned)
        now = utcnow().isoformat()
        with self._connect() as conn:
            current = conn.execute("SELECT id FROM seed_terms WHERE id = ?", (seed_id,)).fetchone()
            if current is None:
                raise ValueError(f"Seed term '{seed_id}' not found.")
            duplicate = conn.execute(
                "SELECT id FROM seed_terms WHERE normalized_term = ? AND id != ?",
                (normalized, seed_id),
            ).fetchone()
            if duplicate is not None:
                raise ValueError(f"Seed term '{cleaned}' already exists.")
            conn.execute(
                """
                UPDATE seed_terms
                SET term = ?, normalized_term = ?, group_key = ?, enabled = ?, priority = ?,
                    tags_json = ?, notes = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    cleaned,
                    normalized,
                    group_key,
                    1 if enabled else 0,
                    priority,
                    json.dumps(tags, ensure_ascii=False),
                    notes,
                    now,
                    seed_id,
                ),
            )
        result = self.get_seed_term_by_id(seed_id)
        assert result is not None
        return result

    def delete_seed_term(self, seed_id: int) -> bool:
        with self._connect() as conn:
            deleted = conn.execute("DELETE FROM seed_terms WHERE id = ?", (seed_id,))
        return deleted.rowcount > 0

    def bulk_replace_seed_terms(self, items: list[dict]) -> list[SeedTermRow]:
        now = utcnow().isoformat()
        rows = []
        seen: set[str] = set()
        for item in items:
            cleaned = normalize_term(item["term"])
            if not cleaned:
                continue
            normalized = canonical_term(cleaned)
            if normalized in seen:
                continue
            seen.add(normalized)
            rows.append(
                (
                    normalized,
                    cleaned,
                    item.get("group_key"),
                    1 if item.get("enabled", True) else 0,
                    int(item.get("priority", 100)),
                    json.dumps(item.get("tags", []), ensure_ascii=False),
                    item.get("notes"),
                    now,
                    now,
                )
            )
        with self._connect() as conn:
            conn.execute("DELETE FROM seed_terms")
            conn.executemany(
                """
                INSERT INTO seed_terms (
                    normalized_term, term, group_key, enabled, priority, tags_json, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        return self.list_all_seed_terms()

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

    def get_run_summary(self, run_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT run_id, started_at, finished_at, status, new_keyword_count,
                       output_json_path, output_csv_path, latest_csv_path, error_message
                FROM runs
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
        return dict(row) if row else None

    def create_run_request(self, request_id: str, requested_at: datetime) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO run_requests (request_id, status, requested_at)
                VALUES (?, ?, ?)
                """,
                (request_id, "pending", requested_at.isoformat()),
            )

    def get_run_request(self, request_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT request_id, status, requested_at, started_at, finished_at, run_id, error_message
                FROM run_requests
                WHERE request_id = ?
                """,
                (request_id,),
            ).fetchone()
        return dict(row) if row else None

    def claim_next_pending_run_request(self, started_at: datetime) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT request_id, status, requested_at, started_at, finished_at, run_id, error_message
                FROM run_requests
                WHERE status = 'pending'
                ORDER BY requested_at ASC
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None
            updated = conn.execute(
                """
                UPDATE run_requests
                SET status = 'running', started_at = ?
                WHERE request_id = ? AND status = 'pending'
                """,
                (started_at.isoformat(), row["request_id"]),
            )
            if updated.rowcount == 0:
                return None
        return self.get_run_request(row["request_id"])

    def finish_run_request(
        self,
        request_id: str,
        *,
        status: str,
        finished_at: datetime,
        run_id: str | None = None,
        error_message: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE run_requests
                SET status = ?, finished_at = ?, run_id = ?, error_message = ?
                WHERE request_id = ?
                """,
                (status, finished_at.isoformat(), run_id, error_message, request_id),
            )
