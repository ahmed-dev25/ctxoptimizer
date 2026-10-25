"""The P0-4 harness itself: fake upstream, streaming and golden runner."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest


async def _wait_until(predicate: Callable[[], bool], max_wait_s: float = 2.0) -> None:
    deadline = time.monotonic() + max_wait_s
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition was not met before the timeout")


def test_fake_upstream_binds_loopback(fake_upstream) -> None:
    assert fake_upstream.base_url.startswith("http://127.0.0.1:")


async def test_json_roundtrip_and_request_recording(fake_upstream) -> None:
    fake_upstream.json({"ok": True})
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{fake_upstream.base_url}/v1/messages?beta=true",
            content=b'{"x":1}',
            headers={"x-api-key": "sk-test"},
        )
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    recorded = fake_upstream.requests[-1]
    assert recorded.method == "POST"
    assert recorded.path == "/v1/messages"
    assert recorded.query == "beta=true"
    assert recorded.body == b'{"x":1}'
    assert recorded.headers["x-api-key"] == "sk-test"


async def test_streaming_preserves_bytes_at_one_byte_chunks(fake_upstream) -> None:
    payload = b"data: one\n\ndata: two\n\ndata: three\n\n"
    fake_upstream.replay(payload, chunk_size=1)
    async with httpx.AsyncClient() as client:
        async with client.stream(
            "GET",
            f"{fake_upstream.base_url}/sse",
            headers={"accept-encoding": "identity"},
        ) as response:
            received = b"".join([chunk async for chunk in response.aiter_raw()])
    assert received == payload
    assert fake_upstream.stream_completed is True


async def test_abrupt_upstream_disconnect_is_observable(fake_upstream) -> None:
    fake_upstream.replay(b"0123456789" * 10, chunk_size=10, disconnect_after=2)
    with pytest.raises(httpx.HTTPError):
        async with httpx.AsyncClient() as client:
            async with client.stream("GET", f"{fake_upstream.base_url}/broken") as response:
                async for _ in response.aiter_raw():
                    pass
    await _wait_until(lambda: fake_upstream.stream_closed)
    assert fake_upstream.stream_completed is False


async def test_client_disconnect_closes_upstream_stream(fake_upstream) -> None:
    fake_upstream.replay(b"0123456789" * 40, chunk_size=10, chunk_delay_s=0.02)
    async with httpx.AsyncClient() as client:
        async with client.stream("GET", f"{fake_upstream.base_url}/stream") as response:
            iterator = response.aiter_raw()
            first = await anext(iterator)
            assert first
    await _wait_until(lambda: fake_upstream.stream_closed)
    assert fake_upstream.stream_completed is False


def test_golden_runner_compares_and_updates(
    golden_factory: Callable[[Path], Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = tmp_path / "case-1"
    case.mkdir()
    (case / "input.json").write_text('{"a": 1}', encoding="utf-8")
    (case / "config.toml").write_text("[demo]\nvalue = 1\n", encoding="utf-8")
    runner = golden_factory(tmp_path)

    def double(payload: dict[str, Any], config_text: str) -> dict[str, Any]:
        assert "value = 1" in config_text
        return {"a": payload["a"] * 2}

    monkeypatch.setenv("UPDATE_GOLDEN", "1")
    runner.run(case, double)
    assert json.loads((case / "expected.json").read_text(encoding="utf-8")) == {"a": 2}

    monkeypatch.delenv("UPDATE_GOLDEN")
    assert runner.run(case, double) == {"a": 2}
    assert runner.cases() == [case]

    def wrong(payload: dict[str, Any], config_text: str) -> dict[str, Any]:
        return {"a": payload["a"] + 10}

    with pytest.raises(AssertionError, match="golden mismatch"):
        runner.run(case, wrong)


def test_db_and_data_fixtures(db_path: Path, data_dir: Path) -> None:
    assert db_path.name == "ctxoptimizer.db"
    assert db_path.parent.is_dir()
    assert data_dir.is_dir()
