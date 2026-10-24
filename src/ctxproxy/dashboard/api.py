"""Admin JSON API (SPEC section 16.3, v0)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ctxproxy.analysis.recommend import recommendations
from ctxproxy.models import WasteFinding

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


def _finding_dict(finding: WasteFinding) -> dict[str, Any]:
    data = asdict(finding)
    data["key_hash"] = finding.key_hash.hex()
    return data


__all__ = [
    "API_VERSION",
    "recent_requests",
    "recommendations_api",
    "summary",
    "waste",
]
