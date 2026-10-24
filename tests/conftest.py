"""Shared test infrastructure (SPEC section 20.1).

Provides a recording fake upstream (real uvicorn server, ephemeral port), an
SSE replay helper with controllable chunking and disconnects, a golden-case
runner, and temp-path fixtures. Later phases build their integration and golden
suites on these fixtures instead of inventing their own harnesses.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import threading
import time
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.routing import Route


@dataclass(slots=True)
class RecordedRequest:
    """One request as the fake upstream saw it."""

    method: str
    path: str
    query: str
    headers: dict[str, str]
    body: bytes


class FakeUpstream:
    """A local Starlette server that records requests and replays responses."""

    def __init__(self) -> None:
        self.requests: list[RecordedRequest] = []
        self.base_url = ""
        self.stream_started = False
        self.stream_closed = False
        self.stream_completed = False
        self._status = 200
        self._headers: dict[str, str] = {"content-type": "application/json"}
        self._body = b"{}"
        self._chunks: list[bytes] | None = None
        self._chunk_delay_s = 0.0
        self._disconnect_after: int | None = None
        self._statuses: list[int] = []
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._socket: socket.socket | None = None

    def reset(self) -> None:
        """Clear recorded requests and stream state between assertions."""
        self.requests.clear()
        self.stream_started = False
        self.stream_closed = False
        self.stream_completed = False
        self._chunks = None
        self._chunk_delay_s = 0.0
        self._disconnect_after = None
        self._statuses = []

    def json(
        self,
        payload: Any,
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Serve one JSON response."""
        self._chunks = None
        self._statuses = []
        self._status = status
        self._body = json.dumps(payload).encode("utf-8")
        self._headers = {"content-type": "application/json", **(headers or {})}

    def replay(
        self,
        data: bytes,
        *,
        chunk_size: int | None = None,
        chunk_delay_s: float = 0.0,
        disconnect_after: int | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Stream *data*, optionally in fixed-size chunks or with a hard cut."""
        if chunk_size is None:
            chunk_size = max(len(data), 1)
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        self._chunks = [data[i : i + chunk_size] for i in range(0, len(data), chunk_size)]
        self._chunk_delay_s = chunk_delay_s
        self._disconnect_after = disconnect_after
        self._status = 200
        self._statuses = []
        self._headers = {"content-type": "text/event-stream", **(headers or {})}

    def sequence(
        self,
        statuses: list[int],
        *,
        body: bytes = b"{}",
        headers: dict[str, str] | None = None,
    ) -> None:
        """Return the given statuses in order, one per request."""
        self._chunks = None
        self._statuses = list(statuses)
        self._body = body
        self._headers = {"content-type": "application/json", **(headers or {})}

    async def _handle(self, request: Request) -> Response:
        body = await request.body()
        self.requests.append(
            RecordedRequest(
                method=request.method,
                path=request.url.path,
                query=request.url.query,
                headers={key.lower(): value for key, value in request.headers.items()},
                body=body,
            )
        )
        status = self._statuses.pop(0) if self._statuses else self._status
        if self._chunks is None:
            return Response(self._body, status_code=status, headers=self._headers)
        return StreamingResponse(self._stream(), status_code=status, headers=self._headers)

    async def _stream(self) -> AsyncIterator[bytes]:
        self.stream_started = True
        completed = False
        try:
            for index, chunk in enumerate(self._chunks or []):
                if self._disconnect_after is not None and index >= self._disconnect_after:
                    raise RuntimeError("simulated upstream failure")
                if self._chunk_delay_s:
                    await asyncio.sleep(self._chunk_delay_s)
                yield chunk
            completed = True
        finally:
            self.stream_closed = True
            self.stream_completed = completed

    def start(self) -> None:
        """Bind an ephemeral loopback port and serve until :meth:`stop`."""
        app = Starlette(
            routes=[
                Route(
                    "/{path:path}",
                    self._handle,
                    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"],
                )
            ]
        )
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        config = uvicorn.Config(
            app,
            log_level="critical",
            access_log=False,
            lifespan="off",
        )
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        deadline = time.monotonic() + 5
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.01)
        if not server.started:
            sock.close()
            raise RuntimeError("fake upstream failed to start")
        self._socket = sock
        self._server = server
        self._thread = thread
        self.base_url = f"http://127.0.0.1:{port}"

    def stop(self) -> None:
        """Ask uvicorn to exit and join the server thread."""
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=5)
        if self._socket is not None:
            self._socket.close()
        self._server = None
        self._thread = None
        self._socket = None


class GoldenRunner:
    """Load, compare and (with ``UPDATE_GOLDEN=1``) rewrite golden cases.

    A case is ``<root>/<name>/{input.json,config.toml,expected.json}``; the
    callable receives the parsed input and the raw config text.
    """

    def __init__(self, root: Path) -> None:
        self.root = root

    def cases(self) -> list[Path]:
        """Return case directories in stable name order."""
        if not self.root.exists():
            return []
        return sorted(
            path
            for path in self.root.iterdir()
            if path.is_dir() and (path / "input.json").is_file()
        )

    def run(self, case: Path, func: Callable[[Any, str], Any]) -> Any:
        """Run *func* over one case and compare or update the expectation."""
        input_payload = json.loads((case / "input.json").read_text(encoding="utf-8"))
        config_path = case / "config.toml"
        config_text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
        actual = func(input_payload, config_text)
        expected_path = case / "expected.json"
        if os.environ.get("UPDATE_GOLDEN") == "1":
            expected_path.write_text(
                json.dumps(actual, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            return actual
        if not expected_path.is_file():
            raise AssertionError(f"golden case {case.name!r} has no expected.json")
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        if actual != expected:
            raise AssertionError(
                f"golden mismatch in {case.name!r}\n"
                f"expected: {json.dumps(expected, sort_keys=True)}\n"
                f"actual:   {json.dumps(actual, sort_keys=True)}"
            )
        return actual


@pytest.fixture
def fake_upstream() -> Iterator[FakeUpstream]:
    """A running fake upstream; stopped and joined after the test."""
    upstream = FakeUpstream()
    upstream.start()
    try:
        yield upstream
    finally:
        upstream.stop()


@pytest.fixture
def golden_root() -> Path:
    """Root of the committed golden corpus."""
    return Path(__file__).parent / "golden"


@pytest.fixture
def golden_factory() -> Callable[[Path], GoldenRunner]:
    """Build a :class:`GoldenRunner` rooted anywhere (usually ``tmp_path``)."""
    return GoldenRunner


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Path for a throwaway SQLite database."""
    return tmp_path / "ctxproxy.db"


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """A throwaway data directory for blobs and the database."""
    path = tmp_path / "data"
    path.mkdir()
    return path
