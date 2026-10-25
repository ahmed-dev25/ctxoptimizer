"""Admin service helpers and doctor checks (P5 support)."""

from __future__ import annotations

from pathlib import Path

from ctxproxy.config import Config
from ctxproxy.dashboard.service import (
    config_view,
    deep_merge,
    findings_from_rows,
    parse_since,
    rows_to_csv,
    write_pricing,
)
from ctxproxy.doctor import run_checks


def test_deep_merge_and_config_view_redacts_token() -> None:
    merged = deep_merge({"a": {"b": 1, "c": 2}}, {"a": {"b": 3}, "d": 4})
    assert merged == {"a": {"b": 3, "c": 2}, "d": 4}
    config = Config.model_validate({"server": {"admin_token": "secret"}})
    view = config_view(config)
    assert view["server"]["admin_token"] == "*" * 3


def test_parse_since_and_csv() -> None:
    assert parse_since("7d") is not None
    assert parse_since("nonsense") is None
    csv_text = rows_to_csv([{"a": 1, "b": "x"}])
    assert "a,b" in csv_text
    assert rows_to_csv([]) == ""


def test_findings_from_rows_and_pricing_write(tmp_path: Path) -> None:
    rows = [
        {
            "finding_id": "f",
            "ts": 1.0,
            "first_seen_ts": 1.0,
            "last_seen_ts": 2.0,
            "session_id": "s",
            "project": None,
            "detector": "redundant_reread",
            "key_hash": "00" * 16,
            "request_id": "r",
            "occurrences": 2,
            "est_tokens_wasted": 10,
            "est_cost_usd": None,
            "status": "new",
            "evidence_json": '{"turn": 1}',
        }
    ]
    findings = findings_from_rows(rows)
    assert findings[0].evidence == {"turn": 1}
    config = Config.model_validate({"pricing": {"file": str(tmp_path / "p.json")}})
    updated, path = write_pricing(
        config, {"models": [{"provider": "test", "match": "m", "input": 1, "output": 2}]}
    )
    assert path.exists()
    assert updated.pricing.file == str(path)


def test_doctor_checks_are_structured(tmp_path: Path) -> None:
    config = Config.model_validate({"telemetry": {"db_path": str(tmp_path / "ctxproxy.db")}})
    checks = run_checks(config, offline=True)
    names = {check.name for check in checks}
    assert {"bind host", "database writable", "pricing", "license"} <= names
