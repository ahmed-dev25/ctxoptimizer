"""SQLite schema, bounded writer thread, retention and purge (SPEC section 14.3).

Request handling never touches SQLite. It enqueues a dict; one writer thread
batches inserts. If the bounded queue is full the event is dropped and counted,
never blocking the proxy (SPEC section 4.3).
"""

from __future__ import annotations

import json
import logging
import os
import queue
import shutil
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from ctxoptimizer.config import data_dir

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 3

_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS sessions(
  session_id TEXT PRIMARY KEY, project TEXT, client TEXT, provider TEXT, kind TEXT,
  first_ts REAL NOT NULL, last_ts REAL NOT NULL, request_count INTEGER NOT NULL DEFAULT 0);

CREATE TABLE IF NOT EXISTS requests(
  request_id TEXT PRIMARY KEY, ts REAL NOT NULL,
  session_id TEXT, project TEXT, client TEXT,
  provider TEXT NOT NULL, endpoint TEXT NOT NULL, upstream TEXT, model TEXT, stream INTEGER,
  mode TEXT NOT NULL, mutated INTEGER NOT NULL DEFAULT 0, fallback_used INTEGER NOT NULL DEFAULT 0,
  config_hash TEXT, status_code INTEGER, outcome TEXT,
  ttfb_ms REAL, total_ms REAL, proxy_overhead_ms REAL,
  orig_bytes INTEGER, final_bytes INTEGER, orig_est_tokens INTEGER, final_est_tokens INTEGER,
  request_headers_json TEXT,
  usage_source TEXT, fresh_input INTEGER, cache_read INTEGER,
  cache_write_5m INTEGER, cache_write_1h INTEGER, cache_write_30m INTEGER, cache_write_12h INTEGER,
  output_tokens INTEGER, reasoning_tokens INTEGER,
  provider_cost_usd REAL, priced INTEGER NOT NULL DEFAULT 0, price_source TEXT,
  cost_actual_usd REAL, cost_baseline_sim_usd REAL, cost_optimized_sim_usd REAL,
  sim_read_baseline INTEGER, sim_read_optimized INTEGER,
  error TEXT);
CREATE INDEX IF NOT EXISTS idx_requests_ts ON requests(ts);
CREATE INDEX IF NOT EXISTS idx_requests_session ON requests(session_id, ts);
CREATE INDEX IF NOT EXISTS idx_requests_project ON requests(project, ts);

CREATE TABLE IF NOT EXISTS transform_reports(
  request_id TEXT NOT NULL REFERENCES requests(request_id) ON DELETE CASCADE,
  transform_id TEXT NOT NULL, changed INTEGER NOT NULL, items_touched INTEGER,
  bytes_before INTEGER, bytes_after INTEGER, est_tokens_saved INTEGER, duration_ms REAL,
  discarded_reason TEXT, error TEXT, notes_json TEXT, fallback INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(request_id, transform_id));

CREATE TABLE IF NOT EXISTS drift_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT NOT NULL, session_id TEXT, ts REAL NOT NULL,
  stream TEXT NOT NULL CHECK(stream IN ('original','final')),
  cause TEXT NOT NULL, at_segment INTEGER, est_tokens_lost INTEGER, detail_json TEXT);

CREATE TABLE IF NOT EXISTS waste_findings(
  finding_id TEXT PRIMARY KEY, ts REAL NOT NULL,
  first_seen_ts REAL NOT NULL, last_seen_ts REAL NOT NULL,
  session_id TEXT, project TEXT, detector TEXT NOT NULL, key_hash TEXT NOT NULL,
  request_id TEXT, occurrences INTEGER NOT NULL DEFAULT 1,
  est_tokens_wasted INTEGER, est_cost_usd REAL,
  status TEXT NOT NULL DEFAULT 'new',
  evidence_json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_waste_session ON waste_findings(session_id, detector);
CREATE INDEX IF NOT EXISTS idx_waste_status ON waste_findings(status, est_cost_usd);

CREATE TABLE IF NOT EXISTS guard_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, session_id TEXT,
  transform_id TEXT NOT NULL, reason TEXT NOT NULL,
  evidence_json TEXT, cleared_ts REAL);

CREATE TABLE IF NOT EXISTS blobs(
  hash TEXT PRIMARY KEY, size INTEGER NOT NULL, created_ts REAL NOT NULL,
  kind TEXT, data BLOB NOT NULL);

CREATE TABLE IF NOT EXISTS captures(
  request_id TEXT NOT NULL, transform_id TEXT, location TEXT, before_hash TEXT, after_hash TEXT);

CREATE TABLE IF NOT EXISTS recommendation_state(
  recommendation_id TEXT PRIMARY KEY, dismissed_until REAL NOT NULL, updated_ts REAL NOT NULL);
"""

_REQUEST_COLUMNS = (
    "request_id",
    "ts",
    "session_id",
    "project",
    "client",
    "provider",
    "endpoint",
    "upstream",
    "model",
    "stream",
    "mode",
    "mutated",
    "fallback_used",
    "config_hash",
    "status_code",
    "outcome",
    "ttfb_ms",
    "total_ms",
    "proxy_overhead_ms",
    "orig_bytes",
    "final_bytes",
    "orig_est_tokens",
    "final_est_tokens",
    "request_headers_json",
    "usage_source",
    "fresh_input",
    "cache_read",
    "cache_write_5m",
    "cache_write_1h",
    "cache_write_30m",
    "cache_write_12h",
    "output_tokens",
    "reasoning_tokens",
    "provider_cost_usd",
    "priced",
    "price_source",
    "cost_actual_usd",
    "cost_baseline_sim_usd",
    "cost_optimized_sim_usd",
    "sim_read_baseline",
    "sim_read_optimized",
    "error",
)

_REQUEST_SQL = (
    f"INSERT OR IGNORE INTO requests({', '.join(_REQUEST_COLUMNS)}) "
    f"VALUES({', '.join('?' for _ in _REQUEST_COLUMNS)})"
)

_SESSION_SQL = """
INSERT INTO sessions(session_id, project, client, provider, kind, first_ts, last_ts, request_count)
VALUES(?, ?, ?, ?, ?, ?, ?, 1)
ON CONFLICT(session_id) DO UPDATE SET
  last_ts = excluded.last_ts,
  request_count = sessions.request_count + 1
"""


class Store:
    """One writer thread, one WAL SQLite file."""

    def __init__(
        self,
        path: Path,
        *,
        queue_max: int = 10_000,
        retention_days: int = 14,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.retention_days = retention_days
        self._queue: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=max(1, queue_max))
        self._dropped = 0
        self._lock = threading.Lock()
        self._last_error: BaseException | None = None
        self._migrate()
        self._thread = threading.Thread(target=self._run, name="ctxoptimizer-store", daemon=True)
        self._thread.start()

    def record_request(self, record: dict[str, Any]) -> bool:
        """Enqueue one request record. Returns False when the queue is full."""
        try:
            self._queue.put_nowait(_normalise(record))
            return True
        except queue.Full:
            with self._lock:
                self._dropped += 1
            return False

    def flush(self) -> None:
        """Block until every queued record has been written."""
        self._queue.join()

    def close(self) -> None:
        """Flush, stop the writer and join it."""
        self._queue.put(None)
        self._queue.join()
        self._thread.join(timeout=5)

    def stats(self) -> dict[str, int]:
        with self._lock:
            dropped = self._dropped
        return {"dropped_events": dropped, "queued": self._queue.qsize()}

    def fetch_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM requests ORDER BY ts DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def count_requests(self) -> int:
        with sqlite3.connect(self.path) as conn:
            return int(conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0])

    def fetch_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM sessions ORDER BY last_ts DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def fetch_session_requests(self, session_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM requests WHERE session_id = ? ORDER BY ts DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def fetch_request(self, request_id: str) -> dict[str, Any] | None:
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM requests WHERE request_id = ?", (request_id,)
            ).fetchone()
        return dict(row) if row is not None else None

    def fetch_transform_reports(self, request_id: str) -> list[dict[str, Any]]:
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM transform_reports WHERE request_id = ? ORDER BY rowid",
                (request_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def fetch_captures(self, request_id: str) -> list[dict[str, Any]]:
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM captures WHERE request_id = ? ORDER BY rowid",
                (request_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def fetch_drift(self, limit: int = 200) -> list[dict[str, Any]]:
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM drift_events ORDER BY ts DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def fetch_guard_events(self, limit: int = 200) -> list[dict[str, Any]]:
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM guard_events ORDER BY ts DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def fetch_waste(self, status: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        query = "SELECT * FROM waste_findings"
        params: list[Any] = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY est_cost_usd DESC, ts DESC LIMIT ?"
        params.append(limit)
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def dismiss_recommendation(
        self, recommendation_id: str, *, days: int = 30, now: float | None = None
    ) -> None:
        current = time.time() if now is None else now
        until = current + max(1, days) * 86_400
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO recommendation_state("
                "recommendation_id, dismissed_until, updated_ts) VALUES(?, ?, ?)",
                (recommendation_id, until, current),
            )
            conn.commit()

    def suppressed_recommendations(self, now: float | None = None) -> set[str]:
        current = time.time() if now is None else now
        with sqlite3.connect(self.path) as conn:
            rows = conn.execute(
                "SELECT recommendation_id FROM recommendation_state WHERE dismissed_until > ?",
                (current,),
            ).fetchall()
        return {str(row[0]) for row in rows}

    def set_waste_status(self, finding_id: str, status: str) -> bool:
        if status not in {"new", "ack", "fixed", "skipped"}:
            return False
        with sqlite3.connect(self.path) as conn:
            cursor = conn.execute(
                "UPDATE waste_findings SET status = ? WHERE finding_id = ?",
                (status, finding_id),
            )
            conn.commit()
        return cursor.rowcount > 0

    def record_guard_event(
        self,
        session_id: str | None,
        transform_id: str,
        reason: str,
        evidence: dict[str, Any] | None = None,
        *,
        cleared_ts: float | None = None,
    ) -> None:
        """Record a quarantine/enable event (rare dashboard write)."""
        try:
            with sqlite3.connect(self.path) as conn:
                conn.execute(
                    "INSERT INTO guard_events("
                    "ts, session_id, transform_id, reason, evidence_json, cleared_ts"
                    ") VALUES(?, ?, ?, ?, ?, ?)",
                    (
                        time.time(),
                        session_id,
                        transform_id,
                        reason,
                        json.dumps(evidence or {}, default=str),
                        cleared_ts,
                    ),
                )
                conn.commit()
        except sqlite3.Error as exc:
            logger.warning("guard event write failed: %s", exc)

    def timeseries(
        self, metric: str, bucket: str = "hour", since_ts: float | None = None
    ) -> list[dict[str, Any]]:
        """Return a bucketed metric series for dashboard charts."""
        columns = {
            "requests": "COUNT(*)",
            "cost": "COALESCE(SUM(cost_actual_usd), 0)",
            "baseline": "COALESCE(SUM(cost_baseline_sim_usd), 0)",
            "fresh": "COALESCE(SUM(fresh_input), 0)",
            "cache_read": "COALESCE(SUM(cache_read), 0)",
            "output": "COALESCE(SUM(output_tokens), 0)",
            "tokens": "COALESCE(SUM(COALESCE(fresh_input, 0) + COALESCE(cache_read, 0) "
            "+ COALESCE(output_tokens, 0)), 0)",
        }
        column = columns.get(metric, "COUNT(*)")
        fmt = "%Y-%m-%dT%H:00:00" if bucket == "hour" else "%Y-%m-%d"
        query = (
            f"SELECT strftime('{fmt}', ts, 'unixepoch') AS bucket, {column} AS value "  # noqa: S608
            "FROM requests"
        )
        params: list[Any] = []
        if since_ts is not None:
            query += " WHERE ts >= ?"
            params.append(since_ts)
        query += " GROUP BY bucket ORDER BY bucket"
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def group_stats(
        self, field: str, limit: int = 20, since_ts: float | None = None
    ) -> list[dict[str, Any]]:
        """Per-project/per-model rollups used by the overview page."""
        column = "project" if field == "project" else "model"
        query = (
            f"SELECT {column} AS name, COUNT(*) AS requests, "  # noqa: S608
            "COALESCE(SUM(cost_actual_usd), 0) AS cost_usd, "
            "COALESCE(SUM(fresh_input), 0) AS fresh_input, "
            "COALESCE(SUM(cache_read), 0) AS cache_read, "
            "COALESCE(SUM(output_tokens), 0) AS output_tokens "
            "FROM requests"
        )
        params: list[Any] = []
        if since_ts is not None:
            query += " WHERE ts >= ?"
            params.append(since_ts)
        query += " GROUP BY name ORDER BY cost_usd DESC LIMIT ?"
        params.append(limit)
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def transform_stats(self) -> list[dict[str, Any]]:
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT transform_id, COUNT(*) AS runs, "
                "COALESCE(SUM(changed), 0) AS changed_runs, "
                "COALESCE(SUM(est_tokens_saved), 0) AS tokens_saved, "
                "COALESCE(AVG(duration_ms), 0) AS avg_ms, "
                "COALESCE(SUM(CASE WHEN discarded_reason = 'error' THEN 1 ELSE 0 END), 0) "
                "AS errors, "
                "COALESCE(SUM(CASE WHEN discarded_reason = 'no_regress' THEN 1 ELSE 0 END), 0) "
                "AS no_regress, "
                "COALESCE(SUM(fallback), 0) AS fallbacks, "
                "MAX(ts) AS last_ts "
                "FROM transform_reports "
                "JOIN requests USING(request_id) "
                "GROUP BY transform_id ORDER BY transform_id"
            ).fetchall()
        return [dict(row) for row in rows]

    def export_rows(self, since_ts: float | None = None, limit: int = 1000) -> list[dict[str, Any]]:
        query = "SELECT * FROM requests"
        params: list[Any] = []
        if since_ts is not None:
            query += " WHERE ts >= ?"
            params.append(since_ts)
        query += " ORDER BY ts DESC LIMIT ?"
        params.append(limit)
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def waste_summary(self, since_ts: float | None = None) -> dict[str, Any]:
        query = (
            "SELECT COUNT(*), COALESCE(SUM(est_tokens_wasted), 0), "
            "COALESCE(SUM(est_cost_usd), 0) FROM waste_findings "
            "WHERE status IN ('new', 'ack')"
        )
        params: list[Any] = []
        if since_ts is not None:
            query += " AND first_seen_ts >= ?"
            params.append(since_ts)
        with sqlite3.connect(self.path) as conn:
            row = conn.execute(query, params).fetchone()
        return {
            "findings": int(row[0]),
            "tokens": int(row[1]),
            "cost_usd": float(row[2]),
        }

    def waste_timeseries(
        self, bucket: str = "day", since_ts: float | None = None
    ) -> list[dict[str, Any]]:
        fmt = "%Y-%m-%dT%H:00:00" if bucket == "hour" else "%Y-%m-%d"
        query = (
            f"SELECT strftime('{fmt}', ts, 'unixepoch') AS bucket, "  # noqa: S608
            "COUNT(*) AS findings, COALESCE(SUM(est_tokens_wasted), 0) AS tokens, "
            "COALESCE(SUM(est_cost_usd), 0) AS cost_usd FROM waste_findings "
            "WHERE status IN ('new', 'ack')"
        )
        params: list[Any] = []
        if since_ts is not None:
            query += " AND first_seen_ts >= ?"
            params.append(since_ts)
        query += " GROUP BY bucket ORDER BY bucket"
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def unpriced(self, limit: int = 100) -> list[dict[str, Any]]:
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT model, provider, COUNT(*) AS requests FROM requests "
                "WHERE priced = 0 AND model IS NOT NULL "
                "GROUP BY model, provider ORDER BY requests DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def summary(self, since_ts: float | None = None, project: str | None = None) -> dict[str, Any]:
        query = (
            "SELECT COUNT(*) AS requests, "
            "COALESCE(SUM(cost_actual_usd), 0.0) AS cost_usd, "
            "COALESCE(SUM(cost_baseline_sim_usd), 0.0) AS baseline_usd, "
            "COALESCE(SUM(fresh_input), 0) AS fresh_input, "
            "COALESCE(SUM(cache_read), 0) AS cache_read, "
            "COALESCE(SUM(output_tokens), 0) AS output_tokens, "
            "COALESCE(SUM(CASE WHEN COALESCE(orig_est_tokens, 0) > "
            "COALESCE(final_est_tokens, 0) THEN orig_est_tokens - final_est_tokens "
            "ELSE 0 END), 0) AS tokens_removed "
            "FROM requests"
        )
        clauses: list[str] = []
        params: list[Any] = []
        if since_ts is not None:
            clauses.append("ts >= ?")
            params.append(since_ts)
        if project:
            clauses.append("project = ?")
            params.append(project)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        with sqlite3.connect(self.path) as conn:
            row = conn.execute(query, params).fetchone()
        return {
            "requests": int(row[0]),
            "cost_usd": float(row[1]),
            "baseline_usd": float(row[2]),
            "fresh_input": int(row[3]),
            "cache_read": int(row[4]),
            "output_tokens": int(row[5]),
            "tokens_removed": int(row[6]),
        }

    def prune(self, retention_days: int | None = None) -> int:
        days = self.retention_days if retention_days is None else retention_days
        cutoff = time.time() - days * 86_400
        with sqlite3.connect(self.path) as conn:
            deleted = conn.execute("DELETE FROM requests WHERE ts < ?", (cutoff,)).rowcount
            conn.execute(
                "DELETE FROM sessions WHERE session_id NOT IN "
                "(SELECT DISTINCT session_id FROM requests)"
            )
            conn.commit()
        return int(deleted)

    def purge(self) -> None:
        with sqlite3.connect(self.path) as conn:
            for statement in (
                "DELETE FROM captures",
                "DELETE FROM blobs",
                "DELETE FROM guard_events",
                "DELETE FROM waste_findings",
                "DELETE FROM drift_events",
                "DELETE FROM transform_reports",
                "DELETE FROM requests",
                "DELETE FROM sessions",
            ):
                conn.execute(statement)
            conn.commit()

    def _migrate(self) -> None:
        conn = sqlite3.connect(self.path)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            version = 0
            if self.path.exists() and self.path.stat().st_size > 0:
                try:
                    row = conn.execute(
                        "SELECT value FROM meta WHERE key = 'schema_version'"
                    ).fetchone()
                except sqlite3.OperationalError:
                    row = None
                version = int(row[0]) if row else 0
                if version < SCHEMA_VERSION:
                    backup = self.path.with_name(f"{self.path.name}.bak-{version}")
                    try:
                        shutil.copy2(self.path, backup)
                    except OSError as exc:
                        logger.warning("database backup failed: %s", exc)
            conn.executescript(_SCHEMA)
            _ensure_column(conn, "requests", "request_headers_json", "TEXT")
            _ensure_column(conn, "transform_reports", "fallback", "INTEGER NOT NULL DEFAULT 0")
            row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
            current = int(row[0]) if row else 0
            if current > SCHEMA_VERSION:
                raise RuntimeError(f"database schema {current} is newer than {SCHEMA_VERSION}")
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
            conn.commit()
        finally:
            conn.close()
        if os.name == "posix":
            os.chmod(self.path, 0o600)

    def _run(self) -> None:
        conn = sqlite3.connect(self.path)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            while True:
                first = self._queue.get()
                if first is None:
                    self._queue.task_done()
                    break
                batch: list[dict[str, Any]] = [first]
                stop = False
                deadline = time.monotonic() + 0.25
                while len(batch) < 100:
                    try:
                        item = self._queue.get_nowait()
                    except queue.Empty:
                        break
                    if item is None:
                        self._queue.task_done()
                        stop = True
                        break
                    batch.append(item)
                    if time.monotonic() >= deadline:
                        break
                try:
                    self._write(conn, batch)
                except Exception as exc:
                    # Telemetry must never take the writer down (SPEC section 4.3).
                    self._last_error = exc
                    logger.warning("telemetry write failed: %s", exc)
                for _ in batch:
                    self._queue.task_done()
                if stop:
                    break
        finally:
            conn.close()

    def _write(self, conn: sqlite3.Connection, batch: list[dict[str, Any]]) -> None:
        conn.executemany(_REQUEST_SQL, [_request_row(record) for record in batch])
        conn.executemany(
            _SESSION_SQL,
            [
                (
                    record.get("session_id") or "unknown",
                    record.get("project"),
                    record.get("client"),
                    record.get("provider"),
                    record.get("kind") or "main",
                    record.get("ts") or time.time(),
                    record.get("ts") or time.time(),
                )
                for record in batch
            ],
        )
        for record in batch:
            request_id = record.get("request_id")
            if not request_id:
                continue
            _insert_reports(conn, request_id, record.get("_transform_reports") or [])
            fallback_ids = record.get("_fallback_transform_ids") or []
            if fallback_ids:
                conn.executemany(
                    "UPDATE transform_reports SET fallback = 1 "
                    "WHERE request_id = ? AND transform_id = ?",
                    [(request_id, transform_id) for transform_id in fallback_ids],
                )
            _insert_drift(conn, request_id, record)
            _insert_findings(conn, record.get("_findings") or [])
            _insert_captures(conn, request_id, record.get("_captures") or [])
        conn.commit()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, declaration: str) -> None:
    names = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in names:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")


def _get(value: object, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _insert_reports(conn: sqlite3.Connection, request_id: str, reports: list[Any]) -> None:
    rows: list[tuple[Any, ...]] = []
    for report in reports:
        before = _get(report, "est_tokens_before", 0) or 0
        after = _get(report, "est_tokens_after", 0) or 0
        notes = _get(report, "notes", {}) or {}
        try:
            notes_json = json.dumps(notes, default=str)
        except (TypeError, ValueError):
            notes_json = "{}"
        rows.append(
            (
                request_id,
                _get(report, "transform_id", "unknown"),
                1 if _get(report, "changed") else 0,
                _get(report, "items_touched", 0),
                _get(report, "bytes_before", 0),
                _get(report, "bytes_after", 0),
                max(int(before) - int(after), 0),
                _get(report, "duration_ms", 0.0),
                _get(report, "discarded_reason"),
                _get(report, "error"),
                notes_json,
            )
        )
    if rows:
        conn.executemany(
            "INSERT OR REPLACE INTO transform_reports("
            "request_id, transform_id, changed, items_touched, bytes_before, "
            "bytes_after, est_tokens_saved, duration_ms, discarded_reason, error, "
            "notes_json) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )


def _insert_drift(conn: sqlite3.Connection, request_id: str, record: dict[str, Any]) -> None:
    drift = record.get("_drift")
    if drift is None:
        return
    conn.execute(
        "INSERT INTO drift_events("
        "request_id, session_id, ts, stream, cause, at_segment, est_tokens_lost, "
        "detail_json) VALUES(?, ?, ?, 'original', ?, ?, ?, ?)",
        (
            request_id,
            record.get("session_id"),
            record.get("ts") or time.time(),
            _get(drift, "cause", "history_mutated"),
            _get(drift, "at_segment"),
            _get(drift, "est_tokens_lost", 0),
            json.dumps(_get(drift, "detail", {}), default=str),
        ),
    )


def _insert_findings(conn: sqlite3.Connection, findings: list[Any]) -> None:
    rows: list[tuple[Any, ...]] = []
    for finding in findings:
        key_hash = _get(finding, "key_hash", b"")
        if isinstance(key_hash, bytes):
            key_hash = key_hash.hex()
        session_id = _get(finding, "session_id")
        detector = _get(finding, "detector", "unknown")
        existing = conn.execute(
            "SELECT finding_id, status FROM waste_findings "
            "WHERE session_id IS ? AND detector = ? AND key_hash = ?",
            (session_id, detector, str(key_hash)),
        ).fetchone()
        if existing is not None:
            conn.execute(
                "UPDATE waste_findings SET last_seen_ts = ?, occurrences = ?, "
                "est_tokens_wasted = MAX(COALESCE(est_tokens_wasted, 0), ?), "
                "est_cost_usd = COALESCE(?, est_cost_usd) "
                "WHERE finding_id = ?",
                (
                    _get(finding, "last_seen_ts", time.time()),
                    _get(finding, "occurrences", 1),
                    _get(finding, "est_tokens_wasted") or 0,
                    _get(finding, "est_cost_usd"),
                    existing[0],
                ),
            )
            continue
        rows.append(
            (
                _get(finding, "finding_id"),
                _get(finding, "ts", time.time()),
                _get(finding, "first_seen_ts", time.time()),
                _get(finding, "last_seen_ts", time.time()),
                session_id,
                _get(finding, "project"),
                detector,
                str(key_hash),
                _get(finding, "request_id"),
                _get(finding, "occurrences", 1),
                _get(finding, "est_tokens_wasted"),
                _get(finding, "est_cost_usd"),
                _get(finding, "status", "new"),
                json.dumps(_get(finding, "evidence", {}), default=str),
            )
        )
    if rows:
        conn.executemany(
            "INSERT OR IGNORE INTO waste_findings("
            "finding_id, ts, first_seen_ts, last_seen_ts, session_id, project, "
            "detector, key_hash, request_id, occurrences, est_tokens_wasted, "
            "est_cost_usd, status, evidence_json) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )


def _insert_captures(conn: sqlite3.Connection, request_id: str, captures: list[Any]) -> None:
    rows = [
        (
            request_id,
            _get(capture, "transform_id"),
            _get(capture, "location"),
            _get(capture, "before_hash"),
            _get(capture, "after_hash"),
        )
        for capture in captures
    ]
    if rows:
        conn.executemany(
            "INSERT INTO captures(request_id, transform_id, location, before_hash, "
            "after_hash) VALUES(?, ?, ?, ?, ?)",
            rows,
        )


def _request_row(record: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(record.get(column) for column in _REQUEST_COLUMNS)


def _normalise(record: dict[str, Any]) -> dict[str, Any]:
    normalised = dict(record)
    if normalised.get("ts") is None:
        normalised["ts"] = time.time()
    for key, fallback in (
        ("session_id", "unknown"),
        ("provider", "unknown"),
        ("endpoint", "passthrough"),
        ("mode", "shadow"),
    ):
        if not normalised.get(key):
            normalised[key] = fallback
    for key in ("mutated", "fallback_used", "priced"):
        if normalised.get(key) is None:
            normalised[key] = 0
    return normalised


def default_db_path() -> Path:
    path = data_dir() / "ctxoptimizer.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


__all__ = ["SCHEMA_VERSION", "Store", "default_db_path"]
