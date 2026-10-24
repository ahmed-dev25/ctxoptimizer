"""Forwarding core: headers, streaming, transforms and error shaping (SPEC 9)."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Mapping
from pathlib import Path
from typing import Any

import httpx
import orjson
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse

from ctxproxy.analysis.session import derive_session_id, project_from_payload
from ctxproxy.analysis.state import AnalysisResult, AnalysisState, observations_from_texts
from ctxproxy.config import Config
from ctxproxy.guard import Guard
from ctxproxy.ids import new_ulid
from ctxproxy.licensing import is_active_mode_allowed
from ctxproxy.models import Endpoint, Mode, Provider, RequestContext, Usage
from ctxproxy.pipeline import PipelineResult, run_pipeline
from ctxproxy.providers import adapter_for
from ctxproxy.routing import Route
from ctxproxy.telemetry.pricing import (
    PriceResult,
    PricingTable,
    load_pricing,
    price_usage,
)
from ctxproxy.telemetry.usage import new_usage_parser
from ctxproxy.transforms import build_transforms
from ctxproxy.transforms.cache_serve import CacheServeState

HOP_BY_HOP = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "proxy-connection",
        "te",
        "trailer",
        "trailers",
        "transfer-encoding",
        "upgrade",
    }
)

_REQUEST_STRIP = frozenset({"host", "content-length", "accept-encoding"})

_TABLES: dict[str, PricingTable] = {}


async def forward(request: Request, route: Route, config: Config) -> Response:
    """Forward one request upstream, optionally applying deterministic transforms."""
    started = time.perf_counter()
    counters = request.app.state.counters
    counters["requests"] += 1
    request_id = new_ulid()
    request.state.request_id = request_id

    raw = await _request_content(request, config)
    content: bytes | AsyncIterator[bytes] = raw
    mutated = False
    pipeline_result: PipelineResult | None = None
    ctx: RequestContext | None = None
    analysis: AnalysisResult | None = None
    if (
        isinstance(raw, bytes)
        and route.endpoint is not Endpoint.PASSTHROUGH
        and route.mode is not Mode.PASSTHROUGH
    ):
        content, mutated, pipeline_result, ctx, analysis = _apply_transforms(
            request, route, config, request_id, raw
        )

    model = (ctx.model if ctx else None) or _extract_model(raw)
    session_id = ctx.session_id if ctx else route.session_id
    project = ctx.project if ctx else route.project
    effective_mode = ctx.mode if ctx else route.mode
    _capture_blobs(request, config, raw, pipeline_result)

    headers = _clean_request_headers(
        request.headers, force_identity=config.http.force_identity_encoding
    )
    client: httpx.AsyncClient = request.app.state.client

    try:
        upstream = await client.send(
            client.build_request(
                request.method,
                route.upstream_url(),
                headers=headers,
                content=content,
            ),
            stream=True,
        )
    except httpx.TimeoutException:
        counters["upstream_errors"] += 1
        return error_response(route.provider, 504, "ctxproxy: upstream timeout")
    except httpx.HTTPError:
        counters["upstream_errors"] += 1
        return error_response(route.provider, 502, "ctxproxy: upstream unreachable")

    fallback_used = False
    if (
        mutated
        and isinstance(raw, bytes)
        and upstream.status_code in config.pipeline.retry_original_on_status
    ):
        await upstream.aclose()
        fallback_used = True
        try:
            upstream = await client.send(
                client.build_request(
                    request.method,
                    route.upstream_url(),
                    headers=headers,
                    content=raw,
                ),
                stream=True,
            )
        except httpx.TimeoutException:
            counters["upstream_errors"] += 1
            return error_response(route.provider, 504, "ctxproxy: upstream timeout")
        except httpx.HTTPError:
            counters["upstream_errors"] += 1
            return error_response(route.provider, 502, "ctxproxy: upstream unreachable")

    ttfb_ms = (time.perf_counter() - started) * 1000
    parser = new_usage_parser(route.provider, route.endpoint, route.profile)

    async def body() -> AsyncIterator[bytes]:
        outcome = "client_disconnect"
        try:
            async for chunk in upstream.aiter_raw():
                try:
                    parser.feed(chunk)
                except Exception:
                    parser.disable()
                yield chunk
            outcome = "completed"
        except Exception:
            outcome = "upstream_error"
            raise
        finally:
            await upstream.aclose()
            total_ms = (time.perf_counter() - started) * 1000
            counters[outcome] += 1
            usage = parser.result()
            priced = _price(usage, route, config, model)
            request.app.state.last_request = {
                "request_id": request_id,
                "upstream": route.upstream_name,
                "provider": route.provider.value,
                "endpoint": route.endpoint.value,
                "model": model,
                "status_code": upstream.status_code,
                "outcome": outcome,
                "mutated": mutated,
                "fallback_used": fallback_used,
                "ttfb_ms": round(ttfb_ms, 3),
                "total_ms": round(total_ms, 3),
                "usage": usage,
                "cost_usd": priced.cost_usd,
                "priced": priced.priced,
                "price_source": priced.source,
                "transform_ids": (
                    [
                        report.transform_id
                        for report in pipeline_result.reports
                        if report.changed and report.discarded_reason is None
                    ]
                    if pipeline_result
                    else []
                ),
                "drift": analysis.drift.cause if analysis and analysis.drift else None,
                "findings": len(analysis.findings) if analysis else 0,
            }
            store = getattr(request.app.state, "store", None)
            if store is not None:
                store.record_request(
                    _store_record(
                        request_id=request_id,
                        route=route,
                        config=config,
                        model=model,
                        raw=raw,
                        content=content,
                        session_id=session_id,
                        project=project,
                        mode=effective_mode,
                        mutated=mutated,
                        fallback_used=fallback_used,
                        status_code=upstream.status_code,
                        outcome=outcome,
                        ttfb_ms=ttfb_ms,
                        total_ms=total_ms,
                        usage=usage,
                        priced=priced,
                    )
                )
            if fallback_used and pipeline_result is not None:
                guard = getattr(request.app.state, "guard", None)
                if isinstance(guard, Guard):
                    guard.observe_fallback(
                        session_id,
                        [
                            report.transform_id
                            for report in pipeline_result.reports
                            if report.changed and report.discarded_reason is None
                        ],
                    )

    return StreamingResponse(
        body(),
        status_code=upstream.status_code,
        headers=_clean_response_headers(upstream.headers, request_id),
    )


def _apply_transforms(
    request: Request,
    route: Route,
    config: Config,
    request_id: str,
    raw: bytes,
) -> tuple[bytes, bool, PipelineResult | None, RequestContext | None, AnalysisResult | None]:
    if request.headers.get("content-encoding"):
        return raw, False, None, None, None
    try:
        payload = orjson.loads(raw)
    except (orjson.JSONDecodeError, TypeError):
        return raw, False, None, None, None
    if not isinstance(payload, dict):
        return raw, False, None, None, None
    adapter = adapter_for(route.provider, route.endpoint)
    if not adapter.is_transformable(payload):
        return raw, False, None, None, None
    mode = route.mode
    if mode is Mode.ACTIVE and not is_active_mode_allowed():
        mode = Mode.SHADOW
    model = adapter.model_of(payload) or _extract_model(raw)
    ctx = RequestContext(
        request_id=request_id,
        provider=route.provider,
        endpoint=route.endpoint,
        upstream_name=route.upstream_name,
        model=model,
        stream=adapter.is_stream(payload),
        mode=mode,
        session_id=(
            route.session_id or derive_session_id(route.provider, request.headers, payload, adapter)
        ),
        project=route.project or project_from_payload(payload, adapter),
        client_name=route.client_name,
        config=config,
        config_hash=config.config_hash,
        started_monotonic=time.monotonic(),
    )
    try:
        guard = getattr(request.app.state, "guard", None)
        disabled = guard.quarantined_for(ctx.session_id) if isinstance(guard, Guard) else set()
        cache_state = getattr(request.app.state, "cache_serve", None)
        transforms = build_transforms(
            config,
            disabled=disabled,
            cache_serve_state=(cache_state if isinstance(cache_state, CacheServeState) else None),
        )
        result = run_pipeline(ctx, payload, adapter, transforms, config)
    except Exception:
        return raw, False, None, ctx, None
    analysis = getattr(request.app.state, "analysis", None)
    analysis_result: AnalysisResult | None = None
    if isinstance(analysis, AnalysisState):
        analysis_result = analysis.observe(
            session_id=ctx.session_id,
            project=ctx.project,
            ts=time.time(),
            segments=result.original_segments,
            observations=observations_from_texts(result.original_texts),
            model=model or "",
            config_hash=ctx.config_hash,
        )
    if mode is Mode.ACTIVE and result.changed:
        return orjson.dumps(payload), True, result, ctx, analysis_result
    return raw, False, result, ctx, analysis_result


async def _request_content(request: Request, config: Config) -> bytes | AsyncIterator[bytes]:
    raw_length = request.headers.get("content-length")
    if raw_length and raw_length.isdigit():
        if int(raw_length) > config.server.max_body_bytes:
            return request.stream()
    return await request.body()


def _capture_blobs(
    request: Request,
    config: Config,
    raw: bytes | AsyncIterator[bytes],
    result: PipelineResult | None,
) -> None:
    capture = config.telemetry.capture_payloads
    if capture == "off" or not isinstance(raw, bytes):
        return
    blobs = getattr(request.app.state, "blobs", None)
    if blobs is None:
        return
    if capture == "full":
        blobs.put(raw)
    elif result is not None:
        for before, _after in result.changed_blocks:
            data = before.encode("utf-8")
            if len(data) >= 2048:
                blobs.put(data)


def _clean_request_headers(headers: Mapping[str, str], *, force_identity: bool) -> dict[str, str]:
    connection = _connection_tokens(headers.get("connection", ""))
    blocked = HOP_BY_HOP | connection | _REQUEST_STRIP
    cleaned: dict[str, str] = {}
    for name, value in headers.items():
        lower = name.lower()
        if lower in blocked or lower.startswith("x-ctxproxy-"):
            continue
        cleaned[name] = value
    if force_identity:
        cleaned["accept-encoding"] = "identity"
    return cleaned


def _clean_response_headers(headers: httpx.Headers, request_id: str) -> dict[str, str]:
    connection = _connection_tokens(headers.get("connection", ""))
    blocked = HOP_BY_HOP | connection | {"content-length", "transfer-encoding"}
    cleaned = {name: value for name, value in headers.items() if name.lower() not in blocked}
    cleaned["x-ctxproxy-request-id"] = request_id
    return cleaned


def _connection_tokens(value: str) -> frozenset[str]:
    return frozenset(token.strip().lower() for token in value.split(",") if token.strip())


def _extract_model(content: bytes | AsyncIterator[bytes]) -> str | None:
    if not isinstance(content, bytes):
        return None
    try:
        payload = orjson.loads(content)
    except (orjson.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    model = payload.get("model")
    return model if isinstance(model, str) else None


def _is_stream(content: bytes | AsyncIterator[bytes]) -> int | None:
    if not isinstance(content, bytes):
        return None
    try:
        payload = orjson.loads(content)
    except (orjson.JSONDecodeError, TypeError):
        return None
    if isinstance(payload, dict):
        return 1 if payload.get("stream") is True else 0
    return None


def _table_for(config: Config) -> PricingTable:
    key = config.pricing.file
    table = _TABLES.get(key)
    if table is None:
        try:
            table = load_pricing(Path(key) if key else None)
        except Exception:
            table = PricingTable([])
        _TABLES[key] = table
    return table


def _price(usage: Usage, route: Route, config: Config, model: str | None) -> PriceResult:
    return price_usage(usage, _table_for(config), route.profile.pricing_provider, model)


def _store_record(
    *,
    request_id: str,
    route: Route,
    config: Config,
    model: str | None,
    raw: bytes | AsyncIterator[bytes],
    content: bytes | AsyncIterator[bytes],
    session_id: str,
    project: str | None,
    mode: Mode,
    mutated: bool,
    fallback_used: bool,
    status_code: int,
    outcome: str,
    ttfb_ms: float,
    total_ms: float,
    usage: Usage,
    priced: PriceResult,
) -> dict[str, Any]:
    raw_size = len(raw) if isinstance(raw, bytes) else None
    final_size = len(content) if isinstance(content, bytes) else raw_size
    return {
        "request_id": request_id,
        "ts": time.time(),
        "session_id": session_id or "unknown",
        "project": project,
        "client": route.client_name,
        "provider": route.provider.value,
        "endpoint": route.endpoint.value,
        "upstream": route.upstream_name,
        "model": model,
        "stream": _is_stream(raw),
        "mode": mode.value,
        "mutated": 1 if mutated else 0,
        "fallback_used": 1 if fallback_used else 0,
        "config_hash": config.config_hash,
        "status_code": status_code,
        "outcome": outcome,
        "ttfb_ms": round(ttfb_ms, 3),
        "total_ms": round(total_ms, 3),
        "orig_bytes": raw_size,
        "final_bytes": final_size,
        "usage_source": usage.source,
        "fresh_input": usage.fresh_input,
        "cache_read": usage.cache_read,
        "cache_write_5m": usage.cache_write_5m,
        "cache_write_1h": usage.cache_write_1h,
        "cache_write_30m": usage.cache_write_30m,
        "cache_write_12h": usage.cache_write_12h,
        "output_tokens": usage.output,
        "reasoning_tokens": usage.reasoning,
        "provider_cost_usd": usage.provider_cost_usd,
        "priced": 1 if priced.priced else 0,
        "price_source": priced.source,
        "cost_actual_usd": priced.cost_usd,
    }


def error_response(provider: Provider, status: int, message: str) -> JSONResponse:
    """Build a provider-shaped proxy-originated error (SPEC section 9.6)."""
    if provider is Provider.ANTHROPIC:
        payload: dict[str, object] = {
            "type": "error",
            "error": {"type": "api_error", "message": message},
        }
    elif provider is Provider.GEMINI:
        payload = {"error": {"code": status, "message": message, "status": "UNAVAILABLE"}}
    elif provider is Provider.OLLAMA:
        payload = {"error": message}
    else:
        code = "upstream_timeout" if status == 504 else "upstream_unreachable"
        payload = {"error": {"message": message, "type": "server_error", "code": code}}
    return JSONResponse(payload, status_code=status)


__all__ = ["error_response", "forward"]
