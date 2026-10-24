"""Starlette application, ingress and health endpoint (SPEC section 4.2).

P1-1 wires classification and health. The forwarding core is injected, so the
server can be tested without a live upstream and P1-2 can supply the real one.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route as StarletteRoute

from ctxproxy import __version__
from ctxproxy.analysis.state import AnalysisState
from ctxproxy.config import Config, data_dir
from ctxproxy.dashboard.api import (
    guard_status,
    recent_requests,
    recommendations_api,
    request_detail,
    session_detail,
    summary,
    waste,
)
from ctxproxy.dashboard.api import (
    pricing as pricing_api,
)
from ctxproxy.dashboard.api import (
    sessions as sessions_api,
)
from ctxproxy.dashboard.api import (
    transforms as transforms_api,
)
from ctxproxy.dashboard.views import (
    live_view,
    overview,
    pricing_view,
    request_view,
    requests_view,
    sessions_view,
    settings_view,
    transforms_view,
    waste_view,
)
from ctxproxy.guard import Guard
from ctxproxy.routing import Route, UnknownUpstream, classify, is_absolute_target
from ctxproxy.telemetry.blobs import BlobStore
from ctxproxy.telemetry.store import Store, default_db_path
from ctxproxy.transforms.cache_serve import CacheServeState

Forwarder = Callable[[Request, Route, Config], Awaitable[Response]]

_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]


def create_app(config: Config, forwarder: Forwarder | None = None) -> Starlette:
    """Build the ASGI app. ``forwarder`` overrides the real proxy core in tests."""

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        app.state.client = _make_client(config)
        app.state.store = _make_store(config)
        app.state.blobs = _make_blobs(config)
        try:
            yield
        finally:
            await app.state.client.aclose()
            if app.state.store is not None:
                app.state.store.close()

    async def health(request: Request) -> Response:
        state = request.app.state
        counters = state.counters
        last = state.last_request or {}
        usage = last.get("usage")
        store = getattr(state, "store", None)
        return JSONResponse(
            {
                "status": "ok",
                "version": __version__,
                "mode": config.mode.default,
                "uptime_s": round(time.monotonic() - state.started, 3),
                "upstreams": sorted(config.upstreams),
                "requests": counters["requests"],
                "completed": counters["completed"],
                "client_disconnect": counters["client_disconnect"],
                "upstream_errors": counters["upstream_errors"],
                "dropped_telemetry": (
                    store.stats()["dropped_events"]
                    if store is not None
                    else counters["dropped_telemetry"]
                ),
                "stored_requests": (store.count_requests() if store is not None else 0),
                "last_model": last.get("model"),
                "last_cost_usd": last.get("cost_usd"),
                "last_priced": last.get("priced", False),
                "last_usage_source": getattr(usage, "source", None),
                "last_mutated": last.get("mutated", False),
                "last_fallback": last.get("fallback_used", False),
                "last_transforms": last.get("transform_ids", []),
                "last_drift": last.get("drift"),
                "last_marker_coverage": (last.get("marker_quality") or {}).get("coverage"),
                "findings": (
                    len(state.analysis.findings())
                    if getattr(state, "analysis", None) is not None
                    else 0
                ),
                "blob_count": (
                    state.blobs.count() if getattr(state, "blobs", None) is not None else 0
                ),
            }
        )

    async def handler(request: Request) -> Response:
        raw_target = request.scope.get("raw_path", b"").decode("latin-1")
        if is_absolute_target(raw_target):
            return JSONResponse(
                {"error": "absolute-form request targets are not supported"},
                status_code=400,
            )
        path = request.url.path
        if path.startswith("/_ctxproxy"):
            return JSONResponse({"error": "not found"}, status_code=404)
        try:
            route = classify(request.method, path, request.url.query, request.headers, config)
        except UnknownUpstream as exc:
            return JSONResponse({"error": str(exc)}, status_code=404)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        active = forwarder or _default_forwarder
        return await active(request, route, config)

    app = Starlette(
        routes=[
            StarletteRoute("/_ctxproxy/health", health, methods=["GET"]),
            StarletteRoute("/_ctxproxy", overview, methods=["GET"]),
            StarletteRoute("/_ctxproxy/", overview, methods=["GET"]),
            StarletteRoute("/_ctxproxy/api/summary", summary, methods=["GET"]),
            StarletteRoute("/_ctxproxy/api/requests", recent_requests, methods=["GET"]),
            StarletteRoute("/_ctxproxy/api/waste", waste, methods=["GET"]),
            StarletteRoute("/_ctxproxy/api/recommend", recommendations_api, methods=["GET"]),
            StarletteRoute("/_ctxproxy/api/sessions", sessions_api, methods=["GET"]),
            StarletteRoute("/_ctxproxy/api/sessions/{session_id}", session_detail, methods=["GET"]),
            StarletteRoute("/_ctxproxy/api/requests/{request_id}", request_detail, methods=["GET"]),
            StarletteRoute("/_ctxproxy/api/transforms", transforms_api, methods=["GET"]),
            StarletteRoute("/_ctxproxy/api/pricing", pricing_api, methods=["GET"]),
            StarletteRoute("/_ctxproxy/api/guard", guard_status, methods=["GET"]),
            StarletteRoute("/_ctxproxy/waste", waste_view, methods=["GET"]),
            StarletteRoute("/_ctxproxy/live", live_view, methods=["GET"]),
            StarletteRoute("/_ctxproxy/sessions", sessions_view, methods=["GET"]),
            StarletteRoute("/_ctxproxy/requests", requests_view, methods=["GET"]),
            StarletteRoute("/_ctxproxy/requests/{request_id}", request_view, methods=["GET"]),
            StarletteRoute("/_ctxproxy/transforms", transforms_view, methods=["GET"]),
            StarletteRoute("/_ctxproxy/pricing", pricing_view, methods=["GET"]),
            StarletteRoute("/_ctxproxy/settings", settings_view, methods=["GET"]),
            StarletteRoute("/{path:path}", handler, methods=_METHODS),
        ],
        lifespan=lifespan,
    )
    app.state.config = config
    app.state.started = time.monotonic()
    app.state.analysis = AnalysisState()
    app.state.guard = Guard(config)
    app.state.cache_serve = CacheServeState(
        config.transforms.cache_serve.max_state_sessions,
        config.transforms.cache_serve.max_entries_per_session,
    )
    app.state.counters = {
        "requests": 0,
        "completed": 0,
        "client_disconnect": 0,
        "upstream_error": 0,
        "upstream_errors": 0,
        "dropped_telemetry": 0,
    }
    app.state.last_request = None
    return app


async def _default_forwarder(request: Request, route: Route, config: Config) -> Response:
    from ctxproxy.proxy import forward

    return await forward(request, route, config)


def _make_client(config: Config) -> httpx.AsyncClient:
    http = config.http
    timeout = httpx.Timeout(
        connect=http.connect_timeout_s,
        read=None if http.read_timeout_s == 0 else http.read_timeout_s,
        write=http.write_timeout_s,
        pool=http.pool_timeout_s,
    )
    return httpx.AsyncClient(
        http2=http.http2,
        trust_env=True,
        follow_redirects=False,
        timeout=timeout,
        limits=httpx.Limits(max_connections=http.max_connections),
    )


def _make_store(config: Config) -> Store | None:
    try:
        path = Path(config.telemetry.db_path) if config.telemetry.db_path else default_db_path()
        return Store(
            path,
            queue_max=config.telemetry.writer_queue_max,
            retention_days=config.telemetry.retention_days,
        )
    except Exception:
        return None


def _make_blobs(config: Config) -> BlobStore | None:
    if config.telemetry.capture_payloads == "off":
        return None
    try:
        return BlobStore(data_dir() / "blobs")
    except Exception:
        return None


__all__ = ["Forwarder", "create_app"]
