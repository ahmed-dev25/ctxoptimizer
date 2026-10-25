"""Expand-usage log (SPEC 12.13).

The MCP server runs in a separate process, so it writes to the same SQLite file
with a tiny direct connection. Content is never logged, only the ref and result.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from ctxproxy.telemetry.store import default_db_path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS expand_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL NOT NULL,
  ref TEXT NOT NULL,
  ok INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_expand_ts ON expand_events(ts);
"""


def record_expand(ref: str, ok: bool, *, db_path: Path | None = None) -> None:
    path = db_path or default_db_path()
    try:
        with sqlite3.connect(path) as conn:
            conn.executescript(_SCHEMA)
            conn.execute(
                "INSERT INTO expand_events(ts, ref, ok) VALUES(?, ?, ?)",
                (time.time(), ref, 1 if ok else 0),
            )
            conn.commit()
    except sqlite3.Error:
        # Expand must still return its result if telemetry is unavailable.
        return


def expand_stats(*, db_path: Path | None = None) -> dict[str, Any]:
    path = db_path or default_db_path()
    try:
        with sqlite3.connect(path) as conn:
            conn.executescript(_SCHEMA)
            row = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(ok), 0), MAX(ts) FROM expand_events"
            ).fetchone()
    except sqlite3.Error:
        return {"total": 0, "ok": 0, "errors": 0, "last_ts": None}
    total = int(row[0])
    ok = int(row[1])
    return {
        "total": total,
        "ok": ok,
        "errors": total - ok,
        "last_ts": row[2],
    }


__all__ = ["expand_stats", "record_expand"]
