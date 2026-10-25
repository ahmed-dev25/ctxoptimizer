"""CLI surface: env, doctor, stats, export and purge (SPEC section 15)."""

from __future__ import annotations

import json
import socket
import time
from pathlib import Path

from typer.testing import CliRunner

from ctxproxy.cli import app
from ctxproxy.telemetry.blobs import BlobStore
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


def test_stats_json_and_project_filter(tmp_path: Path) -> None:
    db_path = tmp_path / "ctxproxy.db"
    _make_db(db_path)
    config = _config(tmp_path, db_path=db_path)
    result = runner.invoke(app, ["stats", "--config", str(config), "--json", "--project", "demo"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["requests"] == 1
    assert payload["cache_hit_ratio"] == 0.6


def test_bench_smoke() -> None:
    result = runner.invoke(app, ["bench", "--rounds", "1"])
    assert result.exit_code == 0
    assert "p50_ms=" in result.stdout


def test_replay_offline(tmp_path: Path) -> None:
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "model": "claude-sonnet-4-5",
                "messages": [
                    {"role": "user", "content": "hello"},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "t1",
                                "content": "\x1b[31mFAILED\x1b[0m\n" * 20,
                            }
                        ],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["replay", str(request)])
    assert result.exit_code == 0
    assert "total:" in result.stdout
    assert "ansi_strip" in result.stdout


def test_capture_exports_redacted_blocks(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CTXPROXY_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "ctxproxy.db"
    blobs = BlobStore(tmp_path / "blobs")
    before = blobs.put(b"OPENAI_API_KEY=sk-secret-value-1234567890")
    after = blobs.put(b"OPENAI_API_KEY=[REDACTED]")
    response = blobs.put(b'{"ok": true}')
    store = Store(db_path)
    store.record_request(
        {
            **_record(),
            "_captures": [
                {
                    "transform_id": "test",
                    "location": "request",
                    "before_hash": before,
                    "after_hash": None,
                },
                {
                    "transform_id": "test",
                    "location": "block-0",
                    "before_hash": before,
                    "after_hash": after,
                },
                {
                    "transform_id": None,
                    "location": "response",
                    "before_hash": response,
                    "after_hash": None,
                },
            ],
        }
    )
    store.flush()
    store.close()
    out = tmp_path / "fixtures"
    config = _config(tmp_path, db_path=db_path)
    result = runner.invoke(app, ["capture", "--out", str(out), "--config", str(config)])
    assert result.exit_code == 0
    blocks = json.loads((out / "req-1" / "blocks.json").read_text(encoding="utf-8"))
    assert "[REDACTED]" in blocks[0]["before"]
    assert "sk-secret" not in blocks[0]["before"]
    assert (out / "req-1" / "request.json").exists()
    assert json.loads((out / "req-1" / "response.json").read_text(encoding="utf-8")) == {"ok": True}


def test_export_json(tmp_path: Path) -> None:
    db_path = tmp_path / "ctxproxy.db"
    _make_db(db_path)
    config = _config(tmp_path, db_path=db_path)
    result = runner.invoke(app, ["export", "--format", "json", "--config", str(config)])
    assert result.exit_code == 0
    assert "req-1" in result.stdout
    assert "deepseek-flash" in result.stdout
    assert "transform_reports" in result.stdout


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
