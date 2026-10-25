"""Admin JSON API (SPEC section 16.3, v0)."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import orjson
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse

from ctxproxy.analysis.break_even import estimate_stale_elision
from ctxproxy.analysis.recommend import recommendations
from ctxproxy.dashboard.service import (
    apply_config_patch,
    config_view,
    findings_from_rows,
    parse_since,
    pricing_payload,
    reload_config,
    rows_to_csv,
    write_pricing,
)
from ctxproxy.models import WasteFinding
from ctxproxy.telemetry.expand import expand_stats as expand_stats_query
from ctxproxy.telemetry.pricing import load_pricing

API_VERSION = 1


async def summary(request: Request) -> Response:
    store = getattr(request.app.state, "store", None)
    data = (
        store.summary(
            parse_since(request.query_params.get("since")),
            request.query_params.get("project"),
        )
        if store is not None
        else {
            "requests": 0,
            "cost_usd": 0.0,
            "fresh_input": 0,
            "cache_read": 0,
            "output_tokens": 0,
            "tokens_removed": 0,
        }
    )
    if store is not None:
        data = dict(data)
        data["waste"] = store.waste_summary(parse_since(request.query_params.get("since")))
    return JSONResponse({"api_version": API_VERSION, **data})


async def admin_config(request: Request) -> Response:
    return JSONResponse(
        {"api_version": API_VERSION, "config": config_view(request.app.state.config)}
    )


async def update_config(request: Request) -> Response:
    try:
        patch = await request.json()
        if not isinstance(patch, dict):
            raise ValueError("config patch must be an object")
        updated = apply_config_patch(request.app, patch)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse({"api_version": API_VERSION, "config": config_view(updated)})


async def reload(request: Request) -> Response:
    try:
        updated = reload_config(request.app)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse({"api_version": API_VERSION, "config": config_view(updated)})


async def set_mode(request: Request) -> Response:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)
    mode = body.get("mode") if isinstance(body, dict) else None
    if mode not in {"passthrough", "shadow", "active"}:
        return JSONResponse(
            {"error": "mode must be passthrough, shadow or active"}, status_code=400
        )
    try:
        updated = apply_config_patch(request.app, {"mode": {"default": mode}})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse({"api_version": API_VERSION, "mode": updated.mode.default})


async def purge(request: Request) -> Response:
    store = getattr(request.app.state, "store", None)
    blobs = getattr(request.app.state, "blobs", None)
    analysis = getattr(request.app.state, "analysis", None)
    if store is not None:
        store.purge()
    if blobs is not None:
        blobs.purge()
    if analysis is not None:
        analysis.clear()
    return JSONResponse({"api_version": API_VERSION, "purged": True})


async def export(request: Request) -> Response:
    store = getattr(request.app.state, "store", None)
    try:
        limit = int(request.query_params.get("limit", "1000"))
    except ValueError:
        limit = 1000
    limit = max(1, min(limit, 100_000))
    rows = (
        store.export_rows(parse_since(request.query_params.get("since")), limit)
        if store is not None
        else []
    )
    if request.query_params.get("format") == "csv":
        return Response(
            rows_to_csv(rows),
            media_type="text/csv",
            headers={"content-disposition": "attachment; filename=ctxproxy-export.csv"},
        )
    return Response(
        orjson.dumps(rows, default=str, option=orjson.OPT_INDENT_2),
        media_type="application/json",
        headers={"content-disposition": "attachment; filename=ctxproxy-export.json"},
    )


async def timeseries(request: Request) -> Response:
    store = getattr(request.app.state, "store", None)
    metric = request.query_params.get("metric", "cost")
    bucket = request.query_params.get("bucket", "hour")
    since = parse_since(request.query_params.get("since"))
    points = store.timeseries(metric, bucket, since) if store is not None else []
    return JSONResponse(
        {"api_version": API_VERSION, "metric": metric, "bucket": bucket, "points": points}
    )


async def drift(request: Request) -> Response:
    store = getattr(request.app.state, "store", None)
    try:
        limit = int(request.query_params.get("limit", "200"))
    except ValueError:
        limit = 200
    rows = store.fetch_drift(max(1, min(limit, 2000))) if store is not None else []
    return JSONResponse({"api_version": API_VERSION, "events": rows})


async def transform_stats(request: Request) -> Response:
    store = getattr(request.app.state, "store", None)
    guard = getattr(request.app.state, "guard", None)
    stats = store.transform_stats() if store is not None else []
    return JSONResponse(
        {
            "api_version": API_VERSION,
            "stats": stats,
            "quarantined": guard.status() if guard is not None else [],
        }
    )


async def request_diff(request: Request) -> Response:
    store = getattr(request.app.state, "store", None)
    blobs = getattr(request.app.state, "blobs", None)
    request_id = request.path_params["request_id"]
    if store is None or blobs is None:
        return JSONResponse({"api_version": API_VERSION, "blocks": []})
    blocks = []
    for capture in store.fetch_captures(request_id):
        before = blobs.get(capture.get("before_hash") or "")
        after = blobs.get(capture.get("after_hash") or "")
        blocks.append(
            {
                "location": capture.get("location"),
                "before": before.decode("utf-8", "replace") if before else None,
                "after": after.decode("utf-8", "replace") if after else None,
            }
        )
    return JSONResponse({"api_version": API_VERSION, "blocks": blocks})


async def live(request: Request) -> Response:
    return StreamingResponse(
        _live_events(request),
        media_type="text/event-stream",
        headers={"cache-control": "no-store"},
    )


async def _live_events(request: Request) -> Any:
    while True:
        if await request.is_disconnected():
            return
        yield "data: " + json.dumps(_live_snapshot(request), default=str) + "\n\n"
        await asyncio.sleep(2.0)


def _live_snapshot(request: Request) -> dict[str, Any]:
    state = request.app.state
    store = getattr(state, "store", None)
    since = time.time() - 300
    recent = store.fetch_recent(20) if store is not None else []
    burn_rows = [row for row in recent if (row.get("ts") or 0) >= since]
    burn = sum(float(row.get("cost_actual_usd") or 0) for row in burn_rows) / 5.0
    sessions = store.fetch_sessions() if store is not None else []
    active = len([row for row in sessions if (row.get("last_ts") or 0) >= since])
    return {
        "api_version": API_VERSION,
        "ts": time.time(),
        "counters": state.counters,
        "active_sessions": active,
        "burn_per_min_usd": burn,
        "last_request": state.last_request or {},
        "recent": recent,
    }


async def waste_status(request: Request) -> Response:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)
    status = body.get("status") if isinstance(body, dict) else None
    if status not in {"new", "ack", "fixed", "skipped"}:
        return JSONResponse({"error": "invalid status"}, status_code=400)
    finding_id = request.path_params["finding_id"]
    store = getattr(request.app.state, "store", None)
    analysis = getattr(request.app.state, "analysis", None)
    updated = store.set_waste_status(finding_id, status) if store is not None else False
    memory_updated = analysis.set_status(finding_id, status) if analysis is not None else False
    if not updated and not memory_updated:
        return JSONResponse({"error": "finding not found"}, status_code=404)
    return JSONResponse({"api_version": API_VERSION, "finding_id": finding_id, "status": status})


async def dismiss_recommendation(request: Request) -> Response:
    store = getattr(request.app.state, "store", None)
    if store is None:
        return JSONResponse({"error": "store unavailable"}, status_code=503)
    recommendation_id = request.path_params["recommendation_id"]
    try:
        body = await request.json()
    except Exception:
        body = {}
    days = int(body.get("days", 30)) if isinstance(body, dict) else 30
    store.dismiss_recommendation(recommendation_id, days=max(1, min(days, 365)))
    return JSONResponse(
        {
            "api_version": API_VERSION,
            "recommendation_id": recommendation_id,
            "dismissed_days": max(1, min(days, 365)),
        }
    )


async def apply_recommendation(request: Request) -> Response:
    recommendation_id = request.path_params["recommendation_id"]
    patches: dict[str, dict[str, Any]] = {
        "enable_cache_serve": {"transforms": {"cache_serve": {"enabled": True}}},
        "enable_volatile_normalizer": {"transforms": {"volatile_normalizer": {"enabled": True}}},
        "enable_transforms": {"mode": {"default": "active"}},
        "batch_reads": {},
        "investigate_runaway": {},
        "prune_mcp_schemas": {},
        "investigate_churn": {},
    }
    patch = patches.get(recommendation_id)
    if patch is None:
        return JSONResponse({"error": "unknown recommendation"}, status_code=404)
    if not patch:
        return JSONResponse(
            {
                "api_version": API_VERSION,
                "applied": False,
                "reason": "advisory only; no automatic config change",
            }
        )
    try:
        updated = apply_config_patch(request.app, patch)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(
        {
            "api_version": API_VERSION,
            "applied": True,
            "config": config_view(updated),
        }
    )


async def put_pricing(request: Request) -> Response:
    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError("pricing payload must be an object")
        config = request.app.state.config
        _updated, path = write_pricing(config, payload)
        apply_config_patch(request.app, {"pricing": {"file": str(path)}})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return JSONResponse(
        {
            "api_version": API_VERSION,
            "pricing": pricing_payload(request.app.state.config),
        }
    )


async def recent_requests(request: Request) -> Response:
    store = getattr(request.app.state, "store", None)
    try:
        limit = int(request.query_params.get("limit", "50"))
    except ValueError:
        limit = 50
    limit = max(1, min(limit, 500))
    rows = store.fetch_recent(limit) if store is not None else []
    for key in ("session_id", "project", "provider", "model", "outcome", "mode"):
        value = request.query_params.get(key)
        if value:
            rows = [row for row in rows if str(row.get(key) or "") == value]
    return JSONResponse({"api_version": API_VERSION, "requests": rows})


async def waste(request: Request) -> Response:
    store = getattr(request.app.state, "store", None)
    analysis = getattr(request.app.state, "analysis", None)
    findings = analysis.findings() if analysis is not None else []
    if not findings and store is not None:
        findings = findings_from_rows(store.fetch_waste())
    return JSONResponse(
        {
            "api_version": API_VERSION,
            "findings": [_finding_dict(finding) for finding in findings],
        }
    )


async def recommendations_api(request: Request) -> Response:
    store = getattr(request.app.state, "store", None)
    analysis = getattr(request.app.state, "analysis", None)
    findings = analysis.findings() if analysis is not None else []
    if not findings and store is not None:
        findings = findings_from_rows(store.fetch_waste())
    config = request.app.state.config
    items = recommendations(
        findings,
        cache_serve_enabled=config.transforms.cache_serve.enabled,
        volatile_normalizer_enabled=config.transforms.volatile_normalizer.enabled,
        transforms_enabled=True,
    )
    suppressed = store.suppressed_recommendations() if store is not None else set()
    items = [item for item in items if item["id"] not in suppressed]
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


async def guard_action(request: Request) -> Response:
    guard = getattr(request.app.state, "guard", None)
    if guard is None:
        return JSONResponse({"error": "guard unavailable"}, status_code=503)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)
    action = body.get("action") if isinstance(body, dict) else None
    transform_id = body.get("transform_id") if isinstance(body, dict) else None
    session_id = body.get("session_id") if isinstance(body, dict) else None
    if not isinstance(transform_id, str) or not transform_id:
        return JSONResponse({"error": "transform_id required"}, status_code=400)
    targets = (
        [session_id]
        if isinstance(session_id, str) and session_id
        else [item["session_id"] for item in guard.status() if item["transform_id"] == transform_id]
    )
    for target in targets:
        if action == "enable":
            guard.enable(target, transform_id)
        elif action == "disable":
            guard.disable(target, transform_id)
        else:
            return JSONResponse({"error": "action must be enable or disable"}, status_code=400)
    return JSONResponse(
        {
            "api_version": API_VERSION,
            "action": action,
            "transform_id": transform_id,
            "sessions": targets,
            "quarantined": guard.status(),
        }
    )


async def stale_estimate(request: Request) -> Response:
    try:
        elided = int(request.query_params.get("elided_tokens", "0"))
        batch = int(request.query_params.get("batch_turns", "8"))
        input_rate = float(request.query_params.get("input_per_mtok", "0"))
        read_rate = float(request.query_params.get("cache_read_per_mtok", "0"))
        write_rate = float(request.query_params.get("cache_write_per_mtok", "0"))
    except ValueError:
        return JSONResponse({"error": "numeric query parameters required"}, status_code=400)
    estimate = estimate_stale_elision(
        elided_tokens=elided,
        batch_turns=batch,
        input_per_mtok=input_rate,
        cache_read_per_mtok=read_rate,
        cache_write_per_mtok=write_rate,
    )
    return JSONResponse(
        {
            "api_version": API_VERSION,
            "label": "sim.",
            "elided_tokens": estimate.elided_tokens,
            "batch_turns": estimate.batch_turns,
            "savings_per_request_usd": estimate.savings_per_request_usd,
            "boundary_miss_cost_usd": estimate.boundary_miss_cost_usd,
            "requests_to_recover": estimate.requests_to_recover,
            "break_even_within_batch": estimate.break_even_within_batch,
            "method": estimate.method,
        }
    )


async def expand_usage(request: Request) -> Response:
    return JSONResponse(
        {"api_version": API_VERSION, "label": "measured", "expand": expand_stats_query()}
    )


def _finding_dict(finding: WasteFinding) -> dict[str, Any]:
    data = asdict(finding)
    data["key_hash"] = finding.key_hash.hex()
    return data


__all__ = [
    "API_VERSION",
    "admin_config",
    "apply_recommendation",
    "dismiss_recommendation",
    "drift",
    "expand_usage",
    "export",
    "guard_action",
    "guard_status",
    "live",
    "pricing",
    "purge",
    "put_pricing",
    "recent_requests",
    "recommendations_api",
    "reload",
    "request_detail",
    "request_diff",
    "session_detail",
    "sessions",
    "set_mode",
    "stale_estimate",
    "summary",
    "timeseries",
    "transform_stats",
    "transforms",
    "update_config",
    "waste",
    "waste_status",
]
