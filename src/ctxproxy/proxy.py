"""Forwarding core: headers, streaming, tee and error shaping (SPEC section 9).

P1-1 ships the signature so the server can be wired and tested. The real
implementation lands in P1-2.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response

from ctxproxy.config import Config
from ctxproxy.routing import Route


async def forward(request: Request, route: Route, config: Config) -> Response:
    """Forward one request upstream. Implemented in P1-2."""
    raise NotImplementedError("forwarding core lands in P1-2")


__all__ = ["forward"]
