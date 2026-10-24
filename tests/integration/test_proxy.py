"""End-to-end proxy core against a real fake upstream."""

from __future__ import annotations

import json
import socket
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest
import uvicorn

from ctxproxy.config import Config
from ctxproxy.models import Provider
from ctxproxy.proxy import error_response
from ctxproxy.server import create_app

FIXTURES = Path(__file__).parents[1] / "fixtures"


@contextmanager
def running_proxy(config: Config) -> Iterator[str]:
    app = create_app(config)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(app, log_level="critical", access_log=False, lifespan="on")
    )
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.01)
    if not server.started:
        raise RuntimeError("proxy failed to start")
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()


@pytest.fixture
def proxy(fake_upstream, tmp_path: Path) -> Iterator[str]:
    config = Config.model_validate(
        {
            "upstreams": {
                "anthropic": fake_upstream.base_url,
                "openai": fake_upstream.base_url,
            },
            "telemetry": {"db_path": str(tmp_path / "ctxproxy.db")},
        }
    )
    with running_proxy(config) as url:
        yield url


def test_non_streaming_passthrough_and_header_hygiene(proxy, fake_upstream) -> None:
    fake_upstream.json({"ok": True})
    with httpx.Client(timeout=10) as client:
        response = client.post(
            f"{proxy}/v1/chat/completions?beta=true",
            content=b'{"x":1}',
            headers={
                "authorization": "Bearer test-token",
                "x-ctxproxy-session": "session-1",
                "connection": "x-remove-me",
                "x-remove-me": "1",
            },
        )
    assert response.status_code == 200
    assert response.content == b'{"ok": true}'
    assert response.headers["x-ctxproxy-request-id"]
    recorded = fake_upstream.requests[-1]
    assert recorded.method == "POST"
    assert recorded.path == "/v1/chat/completions"
    assert recorded.query == "beta=true"
    assert recorded.body == b'{"x":1}'
    assert recorded.headers["authorization"] == "Bearer test-token"
    assert recorded.headers["accept-encoding"] == "identity"
    assert "x-ctxproxy-session" not in recorded.headers
    assert "x-remove-me" not in recorded.headers


def test_streaming_bytes_are_exact(proxy, fake_upstream) -> None:
    payload = b'data: {"n":1}\n\ndata: {"n":2}\n\ndata: [DONE]\n\n'
    fake_upstream.replay(payload, chunk_size=1)
    with httpx.Client(timeout=10) as client:
        with client.stream(
            "POST",
            f"{proxy}/v1/chat/completions",
            content=b'{"stream":true}',
            headers={"accept-encoding": "identity"},
        ) as response:
            received = b"".join(response.iter_raw())
    assert response.status_code == 200
    assert received == payload
    assert fake_upstream.stream_completed is True


def test_upstream_429_passes_through(proxy, fake_upstream) -> None:
    fake_upstream.json(
        {"error": {"message": "rate limited"}},
        status=429,
        headers={"retry-after": "7"},
    )
    with httpx.Client(timeout=10) as client:
        response = client.post(f"{proxy}/v1/messages", content=b"{}")
    assert response.status_code == 429
    assert response.headers["retry-after"] == "7"
    assert response.json()["error"]["message"] == "rate limited"


def test_unknown_path_is_passthrough(proxy, fake_upstream) -> None:
    fake_upstream.json({"ok": True})
    with httpx.Client(timeout=10) as client:
        response = client.post(f"{proxy}/random/path", content=b"raw")
    assert response.status_code == 200
    assert fake_upstream.requests[-1].path == "/random/path"


def test_client_disconnect_closes_upstream_stream(proxy, fake_upstream) -> None:
    fake_upstream.replay(b"0123456789" * 40, chunk_size=10, chunk_delay_s=0.02)
    with httpx.Client(timeout=10) as client:
        with client.stream("POST", f"{proxy}/v1/chat/completions", content=b"{}") as response:
            iterator = response.iter_raw()
            first = next(iterator)
            assert first
    deadline = time.monotonic() + 3
    while not fake_upstream.stream_closed and time.monotonic() < deadline:
        time.sleep(0.02)
    assert fake_upstream.stream_closed is True
    assert fake_upstream.stream_completed is False


def test_health_reports_counters(proxy) -> None:
    with httpx.Client(timeout=10) as client:
        client.post(f"{proxy}/v1/chat/completions", content=b"{}")
        body = client.get(f"{proxy}/_ctxproxy/health").json()
    assert body["requests"] >= 1
    assert body["completed"] >= 1
    assert body["upstream_errors"] == 0


def test_deepseek_usage_and_cost_are_recorded(fake_upstream, tmp_path: Path) -> None:
    config = Config.model_validate(
        {
            "upstreams": {"deepseek": fake_upstream.base_url},
            "telemetry": {"db_path": str(tmp_path / "ctxproxy.db")},
        }
    )
    payload = (FIXTURES / "deepseek" / "chat_stream_usage.sse").read_bytes()
    fake_upstream.replay(payload, chunk_size=20)
    with running_proxy(config) as url:
        with httpx.Client(timeout=10) as client:
            response = client.post(
                f"{url}/u/deepseek/chat/completions",
                content=b'{"model":"deepseek-flash","stream":true}',
            )
            assert response.status_code == 200
            body = client.get(f"{url}/_ctxproxy/health").json()
    assert body["last_model"] == "deepseek-flash"
    assert body["last_usage_source"] == "provider"
    assert body["last_priced"] is True
    expected = (40 * 0.3 + 60 * 0.006 + 10 * 1.2) / 1_000_000
    assert body["last_cost_usd"] == pytest.approx(expected)


def test_non_stream_json_usage_is_parsed(fake_upstream, tmp_path: Path) -> None:
    config = Config.model_validate(
        {
            "upstreams": {"openai": fake_upstream.base_url},
            "telemetry": {"db_path": str(tmp_path / "ctxproxy.db")},
        }
    )
    fake_upstream.json(
        {
            "model": "gpt-6.1-sol",
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "prompt_tokens_details": {"cached_tokens": 2},
            },
        }
    )
    with running_proxy(config) as url:
        with httpx.Client(timeout=10) as client:
            response = client.post(
                f"{url}/v1/chat/completions",
                content=b'{"model":"gpt-6.1-sol"}',
            )
            assert response.status_code == 200
            body = client.get(f"{url}/_ctxproxy/health").json()
    assert body["last_usage_source"] == "provider"


def test_proxy_persists_request_to_sqlite(fake_upstream, tmp_path: Path) -> None:
    db_path = tmp_path / "ctxproxy.db"
    config = Config.model_validate(
        {
            "upstreams": {"openai": fake_upstream.base_url},
            "telemetry": {"db_path": str(db_path)},
        }
    )
    fake_upstream.json({"ok": True})
    with running_proxy(config) as url:
        with httpx.Client(timeout=10) as client:
            response = client.post(
                f"{url}/v1/chat/completions",
                content=b'{"model":"gpt-6.1-sol"}',
            )
            assert response.status_code == 200
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                if client.get(f"{url}/_ctxproxy/health").json()["stored_requests"] >= 1:
                    break
                time.sleep(0.02)
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT model, priced, cost_actual_usd FROM requests").fetchone()
    assert row is not None
    assert row[0] == "gpt-6.1-sol"
    assert row[1] == 1
    assert row[2] is not None


_ANSI = ("\x1b[31m" + "x" * 100 + "\x1b[0m\n") * 50
_ESC_JSON = b"\\u001b"


def _active_payload() -> bytes:
    return json.dumps(
        {
            "model": "claude-sonnet-4-5",
            "messages": [
                {"role": "user", "content": "go"},
                {
                    "role": "assistant",
                    "content": [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {}}],
                },
                {
                    "role": "user",
                    "content": [{"type": "tool_result", "tool_use_id": "t1", "content": _ANSI}],
                },
            ],
        }
    ).encode("utf-8")


def _mode_config(fake_upstream, tmp_path: Path, mode: str) -> Config:
    return Config.model_validate(
        {
            "mode": {"default": mode},
            "upstreams": {"anthropic": fake_upstream.base_url},
            "telemetry": {
                "db_path": str(tmp_path / "ctxproxy.db"),
                "capture_payloads": "off",
            },
        }
    )


def test_active_mode_transforms_request(fake_upstream, tmp_path: Path) -> None:
    fake_upstream.json({"ok": True})
    config = _mode_config(fake_upstream, tmp_path, "active")
    with running_proxy(config) as url:
        with httpx.Client(timeout=10) as client:
            response = client.post(f"{url}/v1/messages", content=_active_payload())
            health = client.get(f"{url}/_ctxproxy/health").json()
    assert response.status_code == 200
    recorded = fake_upstream.requests[-1].body
    assert _ESC_JSON not in recorded
    assert len(recorded) < len(_active_payload())
    assert health["last_mutated"] is True
    assert health["last_transforms"]


def test_shadow_mode_forwards_original(fake_upstream, tmp_path: Path) -> None:
    fake_upstream.json({"ok": True})
    config = _mode_config(fake_upstream, tmp_path, "shadow")
    with running_proxy(config) as url:
        with httpx.Client(timeout=10) as client:
            response = client.post(f"{url}/v1/messages", content=_active_payload())
            health = client.get(f"{url}/_ctxproxy/health").json()
    assert response.status_code == 200
    assert _ESC_JSON in fake_upstream.requests[-1].body
    assert health["last_mutated"] is False


def test_mutated_request_retries_with_original_on_400(fake_upstream, tmp_path: Path) -> None:
    fake_upstream.sequence([400, 200])
    config = _mode_config(fake_upstream, tmp_path, "active")
    with running_proxy(config) as url:
        with httpx.Client(timeout=10) as client:
            response = client.post(f"{url}/v1/messages", content=_active_payload())
            health = client.get(f"{url}/_ctxproxy/health").json()
    assert response.status_code == 200
    assert len(fake_upstream.requests) == 2
    first, second = fake_upstream.requests
    assert _ESC_JSON not in first.body
    assert _ESC_JSON in second.body
    assert health["last_fallback"] is True


def test_changed_blocks_are_stored(fake_upstream, tmp_path: Path, monkeypatch) -> None:
    from ctxproxy.telemetry.blobs import BlobStore

    monkeypatch.setenv("CTXPROXY_DATA_DIR", str(tmp_path / "data"))
    fake_upstream.json({"ok": True})
    config = Config.model_validate(
        {
            "mode": {"default": "active"},
            "upstreams": {"anthropic": fake_upstream.base_url},
            "telemetry": {
                "db_path": str(tmp_path / "ctxproxy.db"),
                "capture_payloads": "changed_blocks",
            },
        }
    )
    with running_proxy(config) as url:
        with httpx.Client(timeout=10) as client:
            assert client.post(f"{url}/v1/messages", content=_active_payload()).status_code == 200
    store = BlobStore(tmp_path / "data" / "blobs")
    assert store.count() >= 1


def test_connect_failure_returns_provider_shaped_502(tmp_path: Path) -> None:
    config = Config.model_validate(
        {
            "upstreams": {
                "anthropic": "http://127.0.0.1:1",
                "openai": "http://127.0.0.1:1",
            },
            "telemetry": {"db_path": str(tmp_path / "ctxproxy.db")},
        }
    )
    with running_proxy(config) as url:
        with httpx.Client(timeout=10) as client:
            response = client.post(f"{url}/v1/messages", content=b"{}")
    assert response.status_code == 502
    payload = response.json()
    assert payload["type"] == "error"
    assert payload["error"]["type"] == "api_error"
    assert "upstream unreachable" in payload["error"]["message"]


@pytest.mark.parametrize(
    ("provider", "status", "expected"),
    [
        (Provider.ANTHROPIC, 502, ("type", "error")),
        (Provider.OPENAI, 504, ("code", "upstream_timeout")),
        (Provider.GEMINI, 502, ("status", "UNAVAILABLE")),
        (Provider.OLLAMA, 502, ("error", "ctxproxy: upstream unreachable")),
    ],
)
def test_error_shapes(provider: Provider, status: int, expected: tuple[str, str]) -> None:
    response = error_response(provider, status, "ctxproxy: upstream unreachable")
    payload = json.loads(response.body)
    if provider is Provider.ANTHROPIC:
        assert payload[expected[0]] == expected[1]
    elif provider is Provider.OPENAI:
        assert payload["error"][expected[0]] == expected[1]
    elif provider is Provider.GEMINI:
        assert payload["error"][expected[0]] == expected[1]
    else:
        assert payload[expected[0]] == expected[1]
