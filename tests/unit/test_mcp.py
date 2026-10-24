"""MCP stdio expand server (P3-9)."""

from __future__ import annotations

from pathlib import Path

from ctxproxy.mcp import handle_message
from ctxproxy.telemetry.blobs import BlobStore


def _store(tmp_path: Path) -> BlobStore:
    return BlobStore(tmp_path / "blobs")


def test_initialize_and_tools_list(tmp_path: Path) -> None:
    blobs = _store(tmp_path)
    init = handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize"}, blobs)
    assert init is not None and init["result"]["serverInfo"]["name"] == "ctxproxy"
    tools = handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, blobs)
    assert tools is not None
    assert tools["result"]["tools"][0]["name"] == "ctxproxy_expand"


def test_expand_returns_original_and_missing_is_honest(tmp_path: Path) -> None:
    blobs = _store(tmp_path)
    ref = blobs.put(b"original bytes")
    response = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "ctxproxy_expand",
                "arguments": {"ref": ref[:8]},
            },
        },
        blobs,
    )
    assert response is not None
    assert response["result"]["content"][0]["text"] == "original bytes"

    missing = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "ctxproxy_expand", "arguments": {"ref": "deadbeef"}},
        },
        blobs,
    )
    assert missing is not None
    assert missing["result"]["isError"] is True


def test_max_tokens_truncates_with_marker(tmp_path: Path) -> None:
    blobs = _store(tmp_path)
    ref = blobs.put(("word " * 2000).encode())
    response = handle_message(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "ctxproxy_expand",
                "arguments": {"ref": ref, "max_tokens": 10},
            },
        },
        blobs,
    )
    assert response is not None
    text = response["result"]["content"][0]["text"]
    assert "[ctxproxy: middle omitted; ref=" in text


def test_notification_is_silent(tmp_path: Path) -> None:
    assert handle_message({"jsonrpc": "2.0", "method": "initialize"}, _store(tmp_path)) is None
