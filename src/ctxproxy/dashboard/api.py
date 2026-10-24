"""Admin JSON API (SPEC section 16.3, v0)."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ctxproxy.analysis.recommend import recommendations
from ctxproxy.models import WasteFinding
from ctxproxy.telemetry.pricing import load_pricing

API_VERSION = 1


async def summary(request: Request) -> Response:
    store = getattr(request.app.state, "store", None)
    data = (
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
    return JSONResponse({"api_version": API_VERSION, **data})


async def recent_requests(request: Request) -> Response:
    store = getattr(request.app.state, "store", None)
    try:
        limit = int(request.query_params.get("limit", "50"))
    except ValueError:
        limit = 50
    limit = max(1, min(limit, 500))
    rows = store.fetch_recent(limit) if store is not None else []
    return JSONResponse({"api_version": API_VERSION, "requests": rows})


async def waste(request: Request) -> Response:
    analysis = getattr(request.app.state, "analysis", None)
    findings = analysis.findings() if analysis is not None else []
    return JSONResponse(
        {
            "api_version": API_VERSION,
            "findings": [_finding_dict(finding) for finding in findings],
        }
    )


async def recommendations_api(request: Request) -> Response:
    analysis = getattr(request.app.state, "analysis", None)
    findings = analysis.findings() if analysis is not None else []
    config = request.app.state.config
    items = recommendations(
        findings,
        cache_serve_enabled=config.transforms.cache_serve.enabled,
        volatile_normalizer_enabled=config.transforms.volatile_normalizer.enabled,
        transforms_enabled=True,
    )
    return JSONResponse({"api_version": API_VERSION, "recommendations": items})


async def sessions(request: Request) -> Response:
    store = getattr(request.app.state, "store", None)
    rows = store.fetch_sessions() if store is not None else []
    return JSONResponse({"api_version": API_VERSION, "sessions": rows})


async def session_detail(request: Request) -> Response:
    store = getattr(request.app.state, "store", None)
    session_id = request.path_params["session_id"]
    rows = store.fetch_session_requests(session_id) if store is not None else []
    return JSONResponse({"api_version": API_VERSION, "session_id": session_id, "requests": rows})


async def request_detail(request: Request) -> Response:
    store = getattr(request.app.state, "store", None)
    request_id = request.path_params["request_id"]
    row = store.fetch_request(request_id) if store is not None else None
    if row is None:
        return JSONResponse({"error": "request not found"}, status_code=404)
    return JSONResponse({"api_version": API_VERSION, "request": row})


async def transforms(request: Request) -> Response:
    config = request.app.state.config
    guard = getattr(request.app.state, "guard", None)
    rows = [
        {"transform": name, **value}
        for name, value in config.transforms.model_dump().items()
        if isinstance(value, dict)
    ]
    return JSONResponse(
        {
            "api_version": API_VERSION,
            "transforms": rows,
            "quarantined": guard.status() if guard is not None else [],
        }
    )


async def pricing(request: Request) -> Response:
    config = request.app.state.config
    table = load_pricing(Path(config.pricing.file) if config.pricing.file else None)
    return JSONResponse(
        {
            "api_version": API_VERSION,
            "version": table.version,
            "currency": table.currency,
            "models": [asdict(model) for model in table.models],
        }
    )


async def guard_status(request: Request) -> Response:
    guard = getattr(request.app.state, "guard", None)
    return JSONResponse(
        {
            "api_version": API_VERSION,
            "quarantined": guard.status() if guard is not None else [],
        }
    )


def _finding_dict(finding: WasteFinding) -> dict[str, Any]:
    data = asdict(finding)
    data["key_hash"] = finding.key_hash.hex()
    return data


__all__ = [
    "API_VERSION",
    "guard_status",
    "pricing",
    "recent_requests",
    "recommendations_api",
    "request_detail",
    "session_detail",
    "sessions",
    "summary",
    "transforms",
    "waste",
]
