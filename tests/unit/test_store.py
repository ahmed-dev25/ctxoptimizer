"""SQLite store: writer thread, overflow, retention and migration."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

import pytest

from ctxproxy.telemetry.store import SCHEMA_VERSION, Store


def _record(index: int, *, ts: float | None = None, cost: float = 0.01) -> dict[str, Any]:
    return {
        "request_id": f"req-{index}",
        "ts": ts if ts is not None else time.time(),
        "session_id": "session-1",
        "project": "project-1",
        "client": "opencode",
        "provider": "openai",
        "endpoint": "chat",
        "upstream": "deepseek",
        "model": "deepseek-flash",
        "stream": 1,
        "mode": "shadow",
        "config_hash": "hash",
        "status_code": 200,
        "outcome": "completed",
        "ttfb_ms": 1.0,
        "total_ms": 2.0,
        "orig_bytes": 10,
        "final_bytes": 10,
        "usage_source": "provider",
        "fresh_input": 40,
        "cache_read": 60,
        "output_tokens": 10,
        "priced": 1,
        "price_source": "pricing",
        "cost_actual_usd": cost,
    }


@pytest.fixture
def store(tmp_path: Path) -> Store:
    instance = Store(tmp_path / "ctxproxy.db")
    try:
        yield instance
    finally:
        instance.close()


def test_roundtrip(store: Store) -> None:
    assert store.record_request(_record(1)) is True
    store.flush()
    rows = store.fetch_recent()
    assert len(rows) == 1
    assert rows[0]["request_id"] == "req-1"
    assert rows[0]["model"] == "deepseek-flash"
    assert rows[0]["priced"] == 1
    assert store.count_requests() == 1


def test_summary(store: Store) -> None:
    store.record_request(_record(1, cost=0.01))
    store.record_request(_record(2, cost=0.02))
    store.flush()
    summary = store.summary()
    assert summary["requests"] == 2
    assert summary["cost_usd"] == pytest.approx(0.03)
    assert summary["fresh_input"] == 80
    assert summary["cache_read"] == 120


def test_duplicate_request_id_is_ignored(store: Store) -> None:
    store.record_request(_record(1))
    store.record_request(_record(1))
    store.flush()
    assert store.count_requests() == 1


def test_prune_removes_old_requests(store: Store) -> None:
    store.record_request(_record(1, ts=time.time() - 10 * 86_400))
    store.record_request(_record(2))
    store.flush()
    deleted = store.prune(1)
    assert deleted == 1
    rows = store.fetch_recent()
    assert [row["request_id"] for row in rows] == ["req-2"]


def test_overflow_drops_without_blocking(tmp_path: Path) -> None:
    instance = Store(tmp_path / "small.db", queue_max=1)
    try:
        started = time.perf_counter()
        for index in range(300):
            instance.record_request(_record(index))
        elapsed = time.perf_counter() - started
        assert elapsed < 1.0
        assert instance.stats()["dropped_events"] > 0
    finally:
        instance.close()


def test_twenty_thousand_row_burst(tmp_path: Path) -> None:
    instance = Store(tmp_path / "burst.db", queue_max=50_000)
    try:
        started = time.perf_counter()
        for index in range(20_000):
            assert instance.record_request(_record(index)) is True
        enqueue_elapsed = time.perf_counter() - started
        assert enqueue_elapsed < 5.0
        instance.flush()
        assert instance.count_requests() == 20_000
    finally:
        instance.close()


def test_migration_from_v0(tmp_path: Path) -> None:
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("INSERT INTO meta VALUES('schema_version', '0')")
    conn.commit()
    conn.close()

    instance = Store(path)
    instance.flush()
    instance.close()

    conn = sqlite3.connect(path)
    row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    conn.close()
    assert row is not None
    assert int(row[0]) == SCHEMA_VERSION


def test_purge_empties_requests(store: Store) -> None:
    store.record_request(_record(1))
    store.flush()
    store.purge()
    assert store.count_requests() == 0
