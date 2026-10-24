"""Forwarding core: headers, streaming, tee and error shaping (SPEC section 9).

The request body is forwarded unchanged in P1. The response is never buffered:
upstream bytes go to the client as they arrive, while a side-channel usage parser
sees a copy and can never raise into the forwarding path (INV-3).
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Mapping
from pathlib import Path
from typing import Any

import httpx
import orjson
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse

from ctxproxy.config import Config
from ctxproxy.ids import new_ulid
from ctxproxy.models import Provider, Usage
from ctxproxy.routing import Route
from ctxproxy.telemetry.pricing import (
    PriceResult,
    PricingTable,
    load_pricing,
    price_usage,
)
from ctxproxy.telemetry.usage import new_usage_parser

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
    """Forward one request upstream and stream the response back."""
    started = time.perf_counter()
    counters = request.app.state.counters
    counters["requests"] += 1
    request_id = new_ulid()
    request.state.request_id = request_id

    content = await _request_content(request, config)
    model = _extract_model(content)
    headers = _clean_request_headers(
        request.headers, force_identity=config.http.force_identity_encoding
    )
    client: httpx.AsyncClient = request.app.state.client

    try:
        upstream_request = client.build_request(
            request.method,
            route.upstream_url(),
            headers=headers,
            content=content,
        )
        upstream = await client.send(upstream_request, stream=True)
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
                "ttfb_ms": round(ttfb_ms, 3),
                "total_ms": round(total_ms, 3),
                "usage": usage,
                "cost_usd": priced.cost_usd,
                "priced": priced.priced,
                "price_source": priced.source,
            }
            store = getattr(request.app.state, "store", None)
            if store is not None:
                store.record_request(
                    _store_record(
                        request_id=request_id,
                        route=route,
                        config=config,
                        model=model,
                        content=content,
                        status_code=upstream.status_code,
                        outcome=outcome,
                        ttfb_ms=ttfb_ms,
                        total_ms=total_ms,
                        usage=usage,
                        priced=priced,
                    )
                )

    return StreamingResponse(
        body(),
        status_code=upstream.status_code,
        headers=_clean_response_headers(upstream.headers, request_id),
    )


async def _request_content(request: Request, config: Config) -> bytes | AsyncIterator[bytes]:
    raw_length = request.headers.get("content-length")
    if raw_length and raw_length.isdigit():
        if int(raw_length) > config.server.max_body_bytes:
            return request.stream()
    return await request.body()


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


def _store_record(
    *,
    request_id: str,
    route: Route,
    config: Config,
    model: str | None,
    content: bytes | AsyncIterator[bytes],
    status_code: int,
    outcome: str,
    ttfb_ms: float,
    total_ms: float,
    usage: Usage,
    priced: PriceResult,
) -> dict[str, Any]:
    size = len(content) if isinstance(content, bytes) else None
    return {
        "request_id": request_id,
        "ts": time.time(),
        "session_id": route.session_id or "unknown",
        "project": route.project,
        "client": route.client_name,
        "provider": route.provider.value,
        "endpoint": route.endpoint.value,
        "upstream": route.upstream_name,
        "model": model,
        "stream": _is_stream(content),
        "mode": route.mode.value,
        "mutated": 0,
        "fallback_used": 0,
        "config_hash": config.config_hash,
        "status_code": status_code,
        "outcome": outcome,
        "ttfb_ms": round(ttfb_ms, 3),
        "total_ms": round(total_ms, 3),
        "orig_bytes": size,
        "final_bytes": size,
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
