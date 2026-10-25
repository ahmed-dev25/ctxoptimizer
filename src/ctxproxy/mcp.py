"""Minimal MCP stdio server exposing ``ctxproxy_expand`` (SPEC 12.13)."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any

from ctxproxy import __version__
from ctxproxy.analysis.tokens import estimate_tokens
from ctxproxy.config import data_dir
from ctxproxy.telemetry.blobs import BlobStore
from ctxproxy.telemetry.expand import record_expand

_PROTOCOL_VERSION = "2024-11-05"


def handle_message(
    message: dict[str, Any],
    blobs: BlobStore,
    on_expand: Callable[[str, bool], None] | None = None,
) -> dict[str, Any] | None:
    """Handle one JSON-RPC message. Notifications return None."""
    request_id = message.get("id")
    method = message.get("method")
    if request_id is None:
        return None
    if method == "initialize":
        result: dict[str, Any] = {
            "protocolVersion": _PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "ctxproxy", "version": __version__},
        }
        return _result(request_id, result)
    if method == "tools/list":
        return _result(
            request_id,
            {
                "tools": [
                    {
                        "name": "ctxproxy_expand",
                        "description": ("Retrieve the original bytes behind a ctxproxy ref."),
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "ref": {"type": "string"},
                                "max_tokens": {"type": "integer"},
                            },
                            "required": ["ref"],
                        },
                    }
                ]
            },
        )
    if method == "tools/call":
        params = message.get("params") or {}
        if params.get("name") != "ctxproxy_expand":
            return _error(request_id, -32602, "unknown tool")
        arguments = params.get("arguments") or {}
        ref = str(arguments.get("ref") or "")
        data = blobs.get(ref)
        if data is None:
            if on_expand is not None:
                on_expand(ref, False)
            return _result(
                request_id,
                {
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"error: no stored blob for ref {ref!r}; "
                                "re-run the tool that produced it"
                            ),
                        }
                    ],
                    "isError": True,
                },
            )
        text = data.decode("utf-8", "replace")
        max_tokens = arguments.get("max_tokens")
        if isinstance(max_tokens, int) and max_tokens > 0 and estimate_tokens(text) > max_tokens:
            head = text[: max_tokens * 2]
            tail = text[-max_tokens * 2 :]
            text = f"{head}\n[ctxproxy: middle omitted; ref={ref}]\n{tail}"
        if on_expand is not None:
            on_expand(ref, True)
        return _result(request_id, {"content": [{"type": "text", "text": text}]})
    return _error(request_id, -32601, f"unknown method: {method}")


def run_stdio() -> None:
    """Serve JSON-RPC over stdin/stdout until EOF."""
    blobs = BlobStore(data_dir() / "blobs")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(message, dict):
            continue
        response = handle_message(message, blobs, on_expand=record_expand)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


def _result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


__all__ = ["handle_message", "run_stdio"]
