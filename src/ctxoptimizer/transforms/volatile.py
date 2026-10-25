"""Experimental volatile-token normalization (SPEC section 12.11).

Opt-in only; it deliberately mutates system text (INV-9). Time values are
reduced to day granularity, UUIDs are replaced, and epoch seconds are removed
only inside ``<env>`` blocks. The function is deterministic and idempotent.
"""

from __future__ import annotations

import re
import time
from typing import Any

from ctxoptimizer.analysis.tokens import estimate_tokens
from ctxoptimizer.config import Config
from ctxoptimizer.models import Provider, RequestContext, TransformReport
from ctxoptimizer.providers.base import ProviderAdapter

_ISO_DAY = re.compile(
    r"\b(\d{4}-\d{2}-\d{2})[T ]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?"
    r"(?:Z|[+-]\d{2}:?\d{2})?\b"
)
_UUID4 = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b"
)
_TIME_ONLY = re.compile(r"(?i)\b(Current time|Time)\s*:\s*\d{1,2}:\d{2}(?::\d{2})?")
_ENV_EPOCH = re.compile(r"(?<!\d)\d{10}(?!\d)")
_ENV_BLOCK = re.compile(r"(?is)<env>.*?</env>")


def normalize_system(text: str) -> str:
    text = _ISO_DAY.sub(r"\1", text)
    text = _UUID4.sub("[uuid]", text)
    text = _TIME_ONLY.sub(r"\1: [time omitted]", text)
    return text


def normalize_user_env(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        block = normalize_system(match.group(0))
        return _ENV_EPOCH.sub("[epoch]", block)

    return _ENV_BLOCK.sub(repl, text)


class VolatileNormalizer:
    id = "volatile_normalizer"

    def applies(
        self, ctx: RequestContext, payload: dict[str, Any], adapter: ProviderAdapter
    ) -> bool:
        return ctx.config.transforms.volatile_normalizer.enabled

    def apply(
        self,
        ctx: RequestContext,
        payload: dict[str, Any],
        adapter: ProviderAdapter,
        config: Config,
    ) -> TransformReport:
        started = time.perf_counter()
        items = 0
        bytes_before = 0
        bytes_after = 0
        tokens_before = 0
        tokens_after = 0
        for target, key, user_text in _text_targets(payload, ctx.provider):
            original = target.get(key)
            if not isinstance(original, str):
                continue
            updated = normalize_user_env(original) if user_text else normalize_system(original)
            if updated == original:
                continue
            target[key] = updated
            items += 1
            bytes_before += len(original.encode("utf-8"))
            bytes_after += len(updated.encode("utf-8"))
            tokens_before += estimate_tokens(original)
            tokens_after += estimate_tokens(updated)
        return TransformReport(
            transform_id=self.id,
            ran=True,
            changed=items > 0,
            items_touched=items,
            bytes_before=bytes_before,
            bytes_after=bytes_after,
            est_tokens_before=tokens_before,
            est_tokens_after=tokens_after,
            duration_ms=(time.perf_counter() - started) * 1000,
        )


def _text_targets(
    payload: dict[str, Any], provider: Provider
) -> list[tuple[dict[str, Any], str, bool]]:
    targets: list[tuple[dict[str, Any], str, bool]] = []
    if provider is Provider.ANTHROPIC:
        system = payload.get("system")
        if isinstance(system, str):
            targets.append((payload, "system", False))
        elif isinstance(system, list):
            targets.extend(
                (block, "text", False)
                for block in system
                if isinstance(block, dict) and isinstance(block.get("text"), str)
            )
    elif provider is Provider.GEMINI:
        system = payload.get("systemInstruction")
        if isinstance(system, dict):
            targets.extend(
                (part, "text", False)
                for part in system.get("parts") or []
                if isinstance(part, dict) and isinstance(part.get("text"), str)
            )
    elif provider is Provider.OLLAMA:
        if isinstance(payload.get("system"), str):
            targets.append((payload, "system", False))

    if provider is Provider.OPENAI and isinstance(payload.get("instructions"), str):
        targets.append((payload, "instructions", False))

    messages = payload.get("messages")
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            content = message.get("content")
            if role in {"system", "developer"}:
                _add_content_targets(targets, message, "content", user_text=False)
            elif role == "user":
                _add_content_targets(targets, message, "content", user_text=True)

    input_items = payload.get("input")
    if isinstance(input_items, list):
        for item in input_items:
            if not isinstance(item, dict):
                continue
            if item.get("role") in {"system", "developer"}:
                _add_content_targets(targets, item, "content", user_text=False)
            elif item.get("role") == "user":
                _add_content_targets(targets, item, "content", user_text=True)

    contents = payload.get("contents")
    if isinstance(contents, list):
        for content in contents:
            if not isinstance(content, dict):
                continue
            if content.get("role") == "user":
                targets.extend(
                    (part, "text", True)
                    for part in content.get("parts") or []
                    if isinstance(part, dict) and isinstance(part.get("text"), str)
                )
    return targets


def _add_content_targets(
    targets: list[tuple[dict[str, Any], str, bool]],
    message: dict[str, Any],
    key: str,
    *,
    user_text: bool,
) -> None:
    content = message.get(key)
    if isinstance(content, str):
        targets.append((message, key, user_text))
    elif isinstance(content, list):
        targets.extend(
            (block, "text", user_text)
            for block in content
            if isinstance(block, dict) and isinstance(block.get("text"), str)
        )


__all__ = ["VolatileNormalizer", "normalize_system", "normalize_user_env"]
