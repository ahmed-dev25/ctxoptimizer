"""CLI surface: env, doctor, stats, export and purge (SPEC section 15)."""

from __future__ import annotations

import socket
import time
from pathlib import Path

from typer.testing import CliRunner

from ctxproxy.cli import app
from ctxproxy.telemetry.store import Store

runner = CliRunner()


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _config(tmp_path: Path, *, db_path: Path, port: int | None = None) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(
        f'[server]\nport = {port or _free_port()}\n[telemetry]\ndb_path = "{db_path.as_posix()}"\n',
        encoding="utf-8",
    )
    return path


def _record() -> dict[str, object]:
    return {
        "request_id": "req-1",
        "ts": time.time(),
        "session_id": "s1",
        "project": "demo",
        "client": "opencode",
        "provider": "deepseek",
        "endpoint": "chat",
        "upstream": "deepseek",
        "model": "deepseek-flash",
        "stream": 1,
        "mode": "shadow",
        "mutated": 0,
        "fallback_used": 0,
        "config_hash": "hash",
        "status_code": 200,
        "outcome": "completed",
        "usage_source": "provider",
        "fresh_input": 40,
        "cache_read": 60,
        "output_tokens": 10,
        "priced": 1,
        "price_source": "pricing",
        "cost_actual_usd": 0.00002436,
    }


def _make_db(path: Path) -> None:
    store = Store(path)
    store.record_request(_record())
    store.flush()
    store.close()


def test_env_bash() -> None:
    result = runner.invoke(app, ["env", "--shell", "bash"])
    assert result.exit_code == 0
    assert 'export ANTHROPIC_BASE_URL="http://127.0.0.1:8787"' in result.stdout
    assert 'export OPENAI_BASE_URL="http://127.0.0.1:8787/v1"' in result.stdout


def test_env_powershell() -> None:
    result = runner.invoke(app, ["env", "--shell", "powershell", "--port", "9000"])
    assert result.exit_code == 0
    assert '$env:ANTHROPIC_BASE_URL = "http://127.0.0.1:9000"' in result.stdout


def test_env_rejects_unknown_shell() -> None:
    result = runner.invoke(app, ["env", "--shell", "cmd"])
    assert result.exit_code != 0


def test_doctor_offline(tmp_path: Path) -> None:
    db_path = tmp_path / "ctxproxy.db"
    config = _config(tmp_path, db_path=db_path)
    result = runner.invoke(app, ["doctor", "--offline", "--config", str(config)])
    assert result.exit_code == 0
    assert "bind host" in result.stdout
    assert "database writable" in result.stdout
    assert "pricing" in result.stdout
    assert "claude-code" in result.stdout


def test_stats_reads_store(tmp_path: Path) -> None:
    db_path = tmp_path / "ctxproxy.db"
    _make_db(db_path)
    config = _config(tmp_path, db_path=db_path)
    result = runner.invoke(app, ["stats", "--config", str(config)])
    assert result.exit_code == 0
    assert "requests: 1" in result.stdout
    assert "cost" in result.stdout


def test_export_json(tmp_path: Path) -> None:
    db_path = tmp_path / "ctxproxy.db"
    _make_db(db_path)
    config = _config(tmp_path, db_path=db_path)
    result = runner.invoke(app, ["export", "--format", "json", "--config", str(config)])
    assert result.exit_code == 0
    assert "req-1" in result.stdout
    assert "deepseek-flash" in result.stdout


def test_export_csv(tmp_path: Path) -> None:
    db_path = tmp_path / "ctxproxy.db"
    _make_db(db_path)
    config = _config(tmp_path, db_path=db_path)
    result = runner.invoke(app, ["export", "--format", "csv", "--config", str(config)])
    assert result.exit_code == 0
    assert "request_id,ts" in result.stdout
    assert "req-1" in result.stdout


def test_purge_all(tmp_path: Path) -> None:
    db_path = tmp_path / "ctxproxy.db"
    _make_db(db_path)
    config = _config(tmp_path, db_path=db_path)
    result = runner.invoke(app, ["purge", "--all", "--config", str(config)])
    assert result.exit_code == 0
    assert "purged" in result.stdout
    result = runner.invoke(app, ["stats", "--config", str(config)])
    assert "requests: 0" in result.stdout


def test_status_unreachable() -> None:
    result = runner.invoke(app, ["status", "--url", "http://127.0.0.1:1"])
    assert result.exit_code == 1
    assert "cannot reach" in (result.stdout + result.stderr)


def test_run_help() -> None:
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "--host" in result.stdout
