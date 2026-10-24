"""SQLite schema, bounded writer thread, retention and purge (SPEC section 14.3).

Request handling never touches SQLite. It enqueues a dict; one writer thread
batches inserts. If the bounded queue is full the event is dropped and counted,
never blocking the proxy (SPEC section 4.3).
"""

from __future__ import annotations

import logging
import os
import queue
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from ctxproxy.config import data_dir

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

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
  discarded_reason TEXT, error TEXT, notes_json TEXT,
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
        self._thread = threading.Thread(target=self._run, name="ctxproxy-store", daemon=True)
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

    def summary(self) -> dict[str, Any]:
        with sqlite3.connect(self.path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS requests, "
                "COALESCE(SUM(cost_actual_usd), 0.0) AS cost_usd, "
                "COALESCE(SUM(fresh_input), 0) AS fresh_input, "
                "COALESCE(SUM(cache_read), 0) AS cache_read, "
                "COALESCE(SUM(output_tokens), 0) AS output_tokens "
                "FROM requests"
            ).fetchone()
        return {
            "requests": int(row[0]),
            "cost_usd": float(row[1]),
            "fresh_input": int(row[2]),
            "cache_read": int(row[3]),
            "output_tokens": int(row[4]),
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
            conn.executescript(_SCHEMA)
            row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
            version = int(row[0]) if row else 0
            if version > SCHEMA_VERSION:
                raise RuntimeError(f"database schema {version} is newer than {SCHEMA_VERSION}")
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
        conn.commit()


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
    path = data_dir() / "ctxproxy.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


__all__ = ["SCHEMA_VERSION", "Store", "default_db_path"]
