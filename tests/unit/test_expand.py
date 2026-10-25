"""Expand usage logging (SPEC 12.13)."""

from __future__ import annotations

from pathlib import Path

from ctxoptimizer.telemetry.expand import expand_stats, record_expand


def test_expand_log_counts_ok_and_errors(tmp_path: Path) -> None:
    db = tmp_path / "ctxoptimizer.db"
    record_expand("abc", True, db_path=db)
    record_expand("def", False, db_path=db)
    stats = expand_stats(db_path=db)
    assert stats["total"] == 2
    assert stats["ok"] == 1
    assert stats["errors"] == 1
    assert stats["last_ts"] is not None
