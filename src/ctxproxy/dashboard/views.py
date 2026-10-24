"""Server-rendered dashboard views (SPEC section 16.2, v0)."""

from __future__ import annotations

from pathlib import Path

from starlette.requests import Request
from starlette.responses import Response
from starlette.templating import Jinja2Templates

from ctxproxy import __version__
from ctxproxy.analysis.recommend import recommendations

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


__all__ = ["overview", "waste_view"]
