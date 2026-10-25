"""Server-rendered dashboard views (SPEC section 16.2)."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.templating import Jinja2Templates

from ctxproxy import __version__
from ctxproxy.analysis.recommend import recommendations
from ctxproxy.config import data_dir
from ctxproxy.dashboard.service import (
    findings_from_rows,
    parse_since,
    pricing_payload,
)
from ctxproxy.doctor import run_checks
from ctxproxy.telemetry.expand import expand_stats

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


async def overview(request: Request) -> Response:
    state = request.app.state
    store = getattr(state, "store", None)
    period = request.query_params.get("period", "7d")
    since = parse_since(period) if period != "all" else None
    summary = (
        store.summary(since)
        if store is not None
        else {
            "requests": 0,
            "cost_usd": 0.0,
            "baseline_usd": 0.0,
            "fresh_input": 0,
            "cache_read": 0,
            "output_tokens": 0,
            "tokens_removed": 0,
        }
    )
    rows = store.export_rows(since, 20) if store is not None else []
    projects = store.group_stats("project", 10, since) if store is not None else []
    models = store.group_stats("model", 10, since) if store is not None else []
    points = store.timeseries("cost", "day", since) if store is not None else []
    waste = (
        store.waste_summary(since)
        if store is not None
        else {
            "findings": 0,
            "tokens": 0,
            "cost_usd": 0.0,
        }
    )
    waste_points = store.waste_timeseries("day", since) if store is not None else []
    spend_line = _polyline([float(point.get("value") or 0) for point in points])
    waste_line = _polyline([float(point.get("cost_usd") or 0) for point in waste_points])
    return templates.TemplateResponse(
        request,
        "overview.html",
        {
            "version": __version__,
            "mode": state.config.mode.default,
            "summary": summary,
            "rows": rows,
            "projects": projects,
            "models": models,
            "points": points,
            "period": period,
            "privacy": state.config.telemetry.capture_payloads != "off",
            "capture": state.config.telemetry.capture_payloads,
            "waste": waste,
            "waste_points": waste_points,
            "spend_line": spend_line,
            "waste_line": waste_line,
        },
    )


async def waste_view(request: Request) -> Response:
    state = request.app.state
    store = getattr(state, "store", None)
    analysis = getattr(state, "analysis", None)
    findings = analysis.findings() if analysis is not None else []
    rows = store.fetch_waste() if store is not None else []
    if not rows:
        rows = [_finding_dict(finding) for finding in findings]
    if not findings and rows:
        findings = findings_from_rows(rows)
    items = recommendations(
        findings,
        cache_serve_enabled=state.config.transforms.cache_serve.enabled,
        volatile_normalizer_enabled=state.config.transforms.volatile_normalizer.enabled,
        transforms_enabled=True,
    )
    suppressed = store.suppressed_recommendations() if store is not None else set()
    items = [item for item in items if item["id"] not in suppressed]
    return templates.TemplateResponse(
        request,
        "waste.html",
        {
            "version": __version__,
            "mode": state.config.mode.default,
            "findings": rows,
            "recommendations": items,
            "csrf": state.csrf_token,
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


async def session_view(request: Request) -> Response:
    store = getattr(request.app.state, "store", None)
    session_id = request.path_params["session_id"]
    rows = (
        list(reversed(store.fetch_session_requests(session_id, 500))) if store is not None else []
    )
    drift = store.fetch_drift(500) if store is not None else []
    by_request = {item["request_id"]: item for item in drift}
    for row in rows:
        row["drift"] = (by_request.get(row["request_id"]) or {}).get("cause")
    ratios = [
        100
        * (row.get("cache_read") or 0)
        / max((row.get("cache_read") or 0) + (row.get("fresh_input") or 0), 1)
        for row in rows
    ]
    return templates.TemplateResponse(
        request,
        "session.html",
        {
            "version": __version__,
            "mode": request.app.state.config.mode.default,
            "title": f"Session {session_id}",
            "session_id": session_id,
            "rows": rows,
            "ratio_line": _polyline(ratios),
        },
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
    reports = store.fetch_transform_reports(request_id) if store is not None else []
    diff = _diff_blocks(request, request_id)
    status_code = 200 if row is not None else 404
    usage = {}
    timing = {}
    headers: dict[str, Any] = {}
    if row is not None:
        try:
            headers = json.loads(row.get("request_headers_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            headers = {}
        usage = {
            key.removeprefix("cache_write_"): row[key]
            for key in row
            if key.startswith("cache_write_")
        }
        usage.update(
            {
                "source": row.get("usage_source"),
                "fresh_input": row.get("fresh_input"),
                "cache_read": row.get("cache_read"),
                "output": row.get("output_tokens"),
                "reasoning": row.get("reasoning_tokens"),
                "provider_cost_usd": row.get("provider_cost_usd"),
            }
        )
        timing = {
            "ttfb_ms": row.get("ttfb_ms"),
            "total_ms": row.get("total_ms"),
            "proxy_overhead_ms": row.get("proxy_overhead_ms"),
        }
    return templates.TemplateResponse(
        request,
        "request.html",
        {
            "version": __version__,
            "mode": request.app.state.config.mode.default,
            "title": f"Request {request_id}",
            "row": row or {},
            "found": row is not None,
            "reports": reports,
            "diff": diff,
            "usage": usage,
            "timing": timing,
            "headers": headers,
        },
        status_code=status_code,
    )


def _diff_blocks(request: Request, request_id: str) -> list[dict[str, Any]]:
    store = getattr(request.app.state, "store", None)
    blobs = getattr(request.app.state, "blobs", None)
    if store is None or blobs is None:
        return []
    blocks: list[dict[str, Any]] = []
    for capture in store.fetch_captures(request_id):
        before = blobs.get(capture.get("before_hash") or "")
        after = blobs.get(capture.get("after_hash") or "")
        blocks.append(
            {
                "location": capture.get("location"),
                "before": before.decode("utf-8", "replace") if before else "",
                "after": after.decode("utf-8", "replace") if after else "",
            }
        )
    return blocks


async def transforms_view(request: Request) -> Response:
    state = request.app.state
    store = getattr(state, "store", None)
    guard = getattr(state, "guard", None)
    stats = {item["transform_id"]: item for item in (store.transform_stats() if store else [])}
    quarantined = {item["transform_id"] for item in (guard.status() if guard else [])}
    rows = [
        {
            "transform": name,
            "enabled": value.get("enabled", False),
            "quarantined": name in quarantined,
            "runs": stats.get(name, {}).get("runs", 0),
            "tokens_saved": stats.get(name, {}).get("tokens_saved", 0),
            "avg_ms": round(float(stats.get(name, {}).get("avg_ms") or 0.0), 3),
            "errors": stats.get(name, {}).get("errors", 0),
            "no_regress": stats.get(name, {}).get("no_regress", 0),
            "fallbacks": stats.get(name, {}).get("fallbacks", 0),
        }
        for name, value in state.config.transforms.model_dump().items()
        if isinstance(value, dict)
    ]
    return templates.TemplateResponse(
        request,
        "transforms.html",
        {
            "version": __version__,
            "mode": state.config.mode.default,
            "rows": rows,
            "guard_events": store.fetch_guard_events() if store else [],
            "expand": expand_stats(),
            "csrf": state.csrf_token,
        },
    )


async def pricing_view(request: Request) -> Response:
    config = request.app.state.config
    payload = pricing_payload(config)
    store = getattr(request.app.state, "store", None)
    unpriced = store.unpriced() if store is not None else []
    return templates.TemplateResponse(
        request,
        "pricing.html",
        {
            "version": __version__,
            "mode": config.mode.default,
            "title": f"Pricing ({payload['version']})",
            "models": payload["models"],
            "payload_json": json.dumps({"models": payload["models"]}, indent=2),
            "unpriced": unpriced,
            "csrf": request.app.state.csrf_token,
        },
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
        "db_path": config.telemetry.db_path or str(data_dir() / "ctxproxy.db"),
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
            "privacy": config.telemetry.capture_payloads != "off",
            "csrf": request.app.state.csrf_token,
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


async def doctor_view(request: Request) -> Response:
    state = request.app.state
    checks = run_checks(state.config, offline=True)
    return templates.TemplateResponse(
        request,
        "doctor.html",
        {
            "version": __version__,
            "mode": state.config.mode.default,
            "title": "Doctor",
            "checks": checks,
        },
    )


def _polyline(values: list[float], width: int = 600, height: int = 80) -> str:
    if len(values) < 2:
        return ""
    maximum = max(max(values), 1e-9)
    step = width / (len(values) - 1)
    return " ".join(
        f"{index * step:.1f},{height - (value / maximum) * height:.1f}"
        for index, value in enumerate(values)
    )


def _finding_dict(finding: Any) -> dict[str, Any]:
    data = asdict(finding)
    data["key_hash"] = finding.key_hash.hex()
    return data


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
            "csrf": request.app.state.csrf_token,
        },
    )


__all__ = [
    "doctor_view",
    "live_view",
    "overview",
    "pricing_view",
    "request_view",
    "requests_view",
    "session_view",
    "sessions_view",
    "settings_view",
    "transforms_view",
    "waste_view",
]
