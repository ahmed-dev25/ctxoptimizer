"""Server-rendered dashboard views (SPEC section 16.2, v0)."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.templating import Jinja2Templates

from ctxproxy import __version__
from ctxproxy.analysis.recommend import recommendations
from ctxproxy.telemetry.pricing import load_pricing

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


async def overview(request: Request) -> Response:
    state = request.app.state
    store = getattr(state, "store", None)
    summary = (
        store.summary()
        if store is not None
        else {
            "requests": 0,
            "cost_usd": 0.0,
            "fresh_input": 0,
            "cache_read": 0,
            "output_tokens": 0,
        }
    )
    rows = store.fetch_recent(20) if store is not None else []
    return templates.TemplateResponse(
        request,
        "overview.html",
        {
            "version": __version__,
            "mode": state.config.mode.default,
            "summary": summary,
            "rows": rows,
        },
    )


async def waste_view(request: Request) -> Response:
    state = request.app.state
    analysis = getattr(state, "analysis", None)
    findings = analysis.findings() if analysis is not None else []
    items = recommendations(
        findings,
        cache_serve_enabled=state.config.transforms.cache_serve.enabled,
        volatile_normalizer_enabled=state.config.transforms.volatile_normalizer.enabled,
        transforms_enabled=True,
    )
    return templates.TemplateResponse(
        request,
        "waste.html",
        {
            "version": __version__,
            "mode": state.config.mode.default,
            "findings": findings,
            "recommendations": items,
        },
    )


async def sessions_view(request: Request) -> Response:
    store = getattr(request.app.state, "store", None)
    rows = store.fetch_sessions() if store is not None else []
    return _table(
        request,
        "Sessions",
        "Grouped by derived session id.",
        [
            ("session_id", "Session"),
            ("project", "Project"),
            ("client", "Client"),
            ("provider", "Provider"),
            ("request_count", "Requests"),
            ("last_ts", "Last seen"),
        ],
        rows,
    )


async def requests_view(request: Request) -> Response:
    store = getattr(request.app.state, "store", None)
    rows = store.fetch_recent(100) if store is not None else []
    return _table(
        request,
        "Requests",
        "Most recent 100 requests.",
        [
            ("request_id", "Request"),
            ("ts", "Time"),
            ("client", "Client"),
            ("provider", "Provider"),
            ("model", "Model"),
            ("fresh_input", "Fresh"),
            ("cache_read", "Cache read"),
            ("output_tokens", "Output"),
            ("cost_actual_usd", "Cost"),
            ("outcome", "Outcome"),
        ],
        rows,
    )


async def request_view(request: Request) -> Response:
    store = getattr(request.app.state, "store", None)
    request_id = request.path_params["request_id"]
    row = store.fetch_request(request_id) if store is not None else None
    status_code = 200 if row is not None else 404
    return templates.TemplateResponse(
        request,
        "request.html",
        {
            "version": __version__,
            "mode": request.app.state.config.mode.default,
            "title": f"Request {request_id}",
            "row": row or {},
            "found": row is not None,
        },
        status_code=status_code,
    )


async def transforms_view(request: Request) -> Response:
    state = request.app.state
    guard = getattr(state, "guard", None)
    quarantined = {item["transform_id"] for item in (guard.status() if guard is not None else [])}
    rows = [
        {
            "transform": name,
            "enabled": value.get("enabled", False),
            "quarantined": name in quarantined,
        }
        for name, value in state.config.transforms.model_dump().items()
        if isinstance(value, dict)
    ]
    return _table(
        request,
        "Transforms",
        "Deterministic transforms and session quarantine state.",
        [
            ("transform", "Transform"),
            ("enabled", "Enabled"),
            ("quarantined", "Quarantined"),
        ],
        rows,
    )


async def pricing_view(request: Request) -> Response:
    config = request.app.state.config
    table = load_pricing(Path(config.pricing.file) if config.pricing.file else None)
    rows = [asdict(model) for model in table.models]
    return _table(
        request,
        f"Pricing ({table.version})",
        "Bundled/overridden rates per million tokens. Unknown models stay unpriced.",
        [
            ("provider", "Provider"),
            ("match", "Model glob"),
            ("input", "Input"),
            ("output", "Output"),
            ("cache_read", "Cache read"),
            ("verified", "Verified"),
        ],
        rows,
    )


async def settings_view(request: Request) -> Response:
    config = request.app.state.config
    data: dict[str, Any] = {
        "host": config.server.host,
        "port": config.server.port,
        "allow_remote": config.server.allow_remote,
        "mode": config.mode.default,
        "capture_payloads": config.telemetry.capture_payloads,
        "retention_days": config.telemetry.retention_days,
        "db_path": config.telemetry.db_path or "(default)",
        "pricing_file": config.pricing.file or "(bundled)",
        "upstreams": {
            name: (entry if isinstance(entry, str) else entry.url)
            for name, entry in config.upstreams.items()
        },
        "config_hash": config.config_hash,
    }
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "version": __version__,
            "mode": config.mode.default,
            "title": "Settings",
            "data": data,
        },
    )


async def live_view(request: Request) -> Response:
    state = request.app.state
    return templates.TemplateResponse(
        request,
        "live.html",
        {
            "version": __version__,
            "mode": state.config.mode.default,
            "counters": state.counters,
            "last": state.last_request or {},
            "quarantined": (
                state.guard.status() if getattr(state, "guard", None) is not None else []
            ),
        },
    )


def _table(
    request: Request,
    title: str,
    subtitle: str,
    columns: list[tuple[str, str]],
    rows: list[dict[str, Any]],
) -> Response:
    return templates.TemplateResponse(
        request,
        "table.html",
        {
            "version": __version__,
            "mode": request.app.state.config.mode.default,
            "title": title,
            "subtitle": subtitle,
            "columns": columns,
            "rows": rows,
        },
    )


__all__ = [
    "live_view",
    "overview",
    "pricing_view",
    "request_view",
    "requests_view",
    "sessions_view",
    "settings_view",
    "transforms_view",
    "waste_view",
]
