"""MCP stdio expand server (P3-9)."""

from __future__ import annotations

from pathlib import Path

from ctxoptimizer.mcp import handle_message
from ctxoptimizer.telemetry.blobs import BlobStore


def _store(tmp_path: Path) -> BlobStore:
    return BlobStore(tmp_path / "blobs")


def test_initialize_and_tools_list(tmp_path: Path) -> None:
    blobs = _store(tmp_path)
    init = handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize"}, blobs)
    assert init is not None and init["result"]["serverInfo"]["name"] == "ctxoptimizer"
    tools = handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, blobs)
    assert tools is not None
    assert tools["result"]["tools"][0]["name"] == "ctxoptimizer_expand"


def test_expand_returns_original_and_missing_is_honest(tmp_path: Path) -> None:
    blobs = _store(tmp_path)
    ref = blobs.put(b"original bytes")
    events: list[tuple[str, bool]] = []
    response = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "ctxoptimizer_expand",
                "arguments": {"ref": ref[:8]},
            },
        },
        blobs,
        on_expand=lambda value, ok: events.append((value, ok)),
    )
    assert response is not None
    assert response["result"]["content"][0]["text"] == "original bytes"
    assert events == [(ref[:8], True)]

    missing = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "ctxoptimizer_expand", "arguments": {"ref": "deadbeef"}},
        },
        blobs,
        on_expand=lambda value, ok: events.append((value, ok)),
    )
    assert missing is not None
    assert missing["result"]["isError"] is True
    assert events[-1] == ("deadbeef", False)


def test_max_tokens_truncates_with_marker(tmp_path: Path) -> None:
    blobs = _store(tmp_path)
    ref = blobs.put(("word " * 2000).encode())
    response = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "ctxoptimizer_expand",
                "arguments": {"ref": ref, "max_tokens": 10},
            },
        },
        blobs,
    )
    assert response is not None
    text = response["result"]["content"][0]["text"]
    assert "[ctxoptimizer: middle omitted; ref=" in text


def test_notification_is_silent(tmp_path: Path) -> None:
    assert handle_message({"jsonrpc": "2.0", "method": "initialize"}, _store(tmp_path)) is None
