"""Anthropic cache_control breakpoint injection (SPEC section 12.9)."""

from __future__ import annotations

import time
from typing import Any

from ctxproxy.config import Config
from ctxproxy.models import Endpoint, Provider, RequestContext, TransformReport
from ctxproxy.providers.base import ProviderAdapter, blocks_of

_CACHEABLE = {"text", "tool_use", "tool_result", "image", "document"}


class AnthropicCache:
    id = "anthropic_cache"

    def applies(
        self, ctx: RequestContext, payload: dict[str, Any], adapter: ProviderAdapter
    ) -> bool:
        return (
            ctx.config.transforms.anthropic_cache.enabled
            and ctx.provider is Provider.ANTHROPIC
            and ctx.endpoint is Endpoint.MESSAGES
        )

    def apply(
        self,
        ctx: RequestContext,
        payload: dict[str, Any],
        adapter: ProviderAdapter,
        config: Config,
    ) -> TransformReport:
        started = time.perf_counter()
        settings = config.transforms.anthropic_cache
        existing = _count_markers(payload)
        remaining = settings.max_breakpoints - existing
        added: list[str] = []
        if remaining > 0:
            system = payload.get("system")
            if isinstance(system, str):
                payload["system"] = [{"type": "text", "text": system}]
                system = payload["system"]
            if isinstance(system, list) and _mark_last(system, settings.ttl, added):
                remaining -= 1
            elif not system:
                tools = payload.get("tools")
                if isinstance(tools, list) and tools and remaining > 0:
                    if _mark_last(tools, settings.ttl, added):
                        remaining -= 1
            messages = payload.get("messages")
            if isinstance(messages, list) and remaining > 0 and len(messages) >= 3:
                if _mark_last(blocks_of(messages[-3].get("content")), settings.ttl, added):
                    remaining -= 1
            if isinstance(messages, list) and remaining > 0 and messages:
                if _mark_last(blocks_of(messages[-1].get("content")), settings.ttl, added):
                    remaining -= 1
        return TransformReport(
            transform_id=self.id,
            ran=True,
            changed=bool(added),
            items_touched=len(added),
            duration_ms=(time.perf_counter() - started) * 1000,
            notes={"added": added, "existing": existing},
        )


def _count_markers(payload: dict[str, Any]) -> int:
    total = 0
    for block in payload.get("tools") or []:
        if isinstance(block, dict) and "cache_control" in block:
            total += 1
    system = payload.get("system")
    if isinstance(system, list):
        total += sum(1 for block in system if isinstance(block, dict) and "cache_control" in block)
    for message in payload.get("messages") or []:
        if not isinstance(message, dict):
            continue
        total += sum(1 for block in blocks_of(message.get("content")) if "cache_control" in block)
    return total


def _mark_last(blocks: list[dict[str, Any]], ttl: str, added: list[str]) -> bool:
    for block in reversed(blocks):
        if block.get("type") not in _CACHEABLE:
            continue
        if block.get("type") == "text" and not block.get("text"):
            continue
        if "cache_control" in block:
            return False
        marker: dict[str, Any] = {"type": "ephemeral"}
        if ttl == "1h":
            marker["ttl"] = "1h"
        block["cache_control"] = marker
        added.append(str(block.get("type")))
        return True
    return False


__all__ = ["AnthropicCache"]
