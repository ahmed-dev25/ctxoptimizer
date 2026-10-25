"""Opt-in stale tool-result elision (SPEC section 12.8, P6-4)."""

from __future__ import annotations

import time
from typing import Any

from ctxoptimizer.config import Config
from ctxoptimizer.models import RequestContext, TransformReport
from ctxoptimizer.providers.base import ProviderAdapter


class StaleResultElision:
    id = "stale_result_elision"

    def applies(
        self, ctx: RequestContext, payload: dict[str, Any], adapter: ProviderAdapter
    ) -> bool:
        return ctx.config.transforms.stale_result_elision.enabled

    def apply(
        self,
        ctx: RequestContext,
        payload: dict[str, Any],
        adapter: ProviderAdapter,
        config: Config,
    ) -> TransformReport:
        started = time.perf_counter()
        settings = config.transforms.stale_result_elision
        turns = assistant_turns(payload)
        boundary = max(
            0,
            ((turns - settings.keep_recent_turns) // settings.batch_turns) * settings.batch_turns,
        )
        turn_by_index = _turn_by_index(payload)
        touched = 0
        before = 0
        after = 0
        for ref in adapter.iter_tool_results(payload):
            text = ref.get_text()
            if text is None or text.startswith("[ctxoptimizer:"):
                continue
            size = len(text.encode("utf-8"))
            if size < settings.min_bytes:
                continue
            turn = turn_by_index.get(ref.message_index, turns)
            if turn >= boundary:
                continue
            stub = (
                f"[ctxoptimizer: tool result elided ({size / 1024:.1f} KB); "
                "re-run the tool if needed]"
            )
            if len(stub.encode("utf-8")) >= size:
                continue
            before += size
            after += len(stub.encode("utf-8"))
            ref.set_text(stub)
            touched += 1
        return TransformReport(
            transform_id=self.id,
            ran=True,
            changed=touched > 0,
            items_touched=touched,
            bytes_before=before,
            bytes_after=after,
            duration_ms=(time.perf_counter() - started) * 1000,
            notes={"boundary": boundary, "turns": turns, "elided": touched},
        )


def assistant_turns(payload: dict[str, Any]) -> int:
    return sum(1 for item in _items(payload) if _is_assistant(item))


def _turn_by_index(payload: dict[str, Any]) -> dict[int, int]:
    turns = 0
    result: dict[int, int] = {}
    for index, item in enumerate(_items(payload)):
        if _is_assistant(item):
            turns += 1
        result[index] = turns
    return result


def _items(payload: dict[str, Any]) -> list[Any]:
    value = payload.get("messages")
    if isinstance(value, list):
        return value
    value = payload.get("contents")
    if isinstance(value, list):
        return value
    value = payload.get("input")
    if isinstance(value, str):
        return [{"type": "message", "role": "user", "content": value}]
    return value if isinstance(value, list) else []


def _is_assistant(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    if item.get("type") == "function_call":
        return True
    role = item.get("role")
    if role is None and item.get("type") == "message":
        role = item.get("role")
    return role in {"assistant", "model"}


__all__ = ["StaleResultElision", "assistant_turns"]
