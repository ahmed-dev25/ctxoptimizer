"""Conservative tool-edit extraction for the opt-in churn detector (W7).

Only argument dictionaries with a known old/new string pair are inspected. Raw
edit text stays in memory for the current request and is never persisted.
"""

from __future__ import annotations

from typing import Any

import orjson

from ctxoptimizer.analysis.tokens import estimate_tokens
from ctxoptimizer.analysis.waste import EditObservation
from ctxoptimizer.models import Provider
from ctxoptimizer.providers.base import blocks_of

_PAIRS: tuple[tuple[str, str], ...] = (
    ("old_string", "new_string"),
    ("oldText", "newText"),
    ("old_str", "new_str"),
    ("old_content", "new_content"),
    ("search", "replace"),
    ("old", "new"),
)
_PATH_KEYS = ("file_path", "path", "filename", "file", "target_file")


def edit_observations(payload: dict[str, Any], provider: Provider) -> list[EditObservation]:
    observations: list[EditObservation] = []
    for tool_name, arguments in _tool_inputs(payload, provider):
        if not isinstance(arguments, dict):
            continue
        path = _path_of(arguments) or tool_name or "<unknown>"
        for old_key, new_key in _PAIRS:
            old = arguments.get(old_key)
            new = arguments.get(new_key)
            if not isinstance(old, str) or not isinstance(new, str):
                continue
            observations.append(
                EditObservation(
                    path=path,
                    old=old,
                    new=new,
                    tool_name=tool_name,
                    tokens=max(estimate_tokens(old), estimate_tokens(new)),
                )
            )
            break
    return observations


def _tool_inputs(payload: dict[str, Any], provider: Provider) -> list[tuple[str | None, object]]:
    if provider is Provider.ANTHROPIC:
        return _anthropic_inputs(payload)
    if provider is Provider.GEMINI:
        return _gemini_inputs(payload)
    if provider is Provider.OLLAMA:
        return _chat_inputs(payload)
    return _openai_inputs(payload)


def _anthropic_inputs(payload: dict[str, Any]) -> list[tuple[str | None, object]]:
    result: list[tuple[str | None, object]] = []
    result.extend(
        (
            block.get("name") if isinstance(block.get("name"), str) else None,
            block.get("input"),
        )
        for message in payload.get("messages") or []
        if isinstance(message, dict)
        for block in blocks_of(message.get("content"))
        if block.get("type") == "tool_use"
    )
    return result


def _openai_inputs(payload: dict[str, Any]) -> list[tuple[str | None, object]]:
    result: list[tuple[str | None, object]] = []
    result.extend(
        (
            item.get("name") if isinstance(item.get("name"), str) else None,
            _arguments(item.get("arguments")),
        )
        for item in payload.get("input") or []
        if isinstance(item, dict) and item.get("type") == "function_call"
    )
    result.extend(_chat_inputs(payload))
    return result


def _chat_inputs(payload: dict[str, Any]) -> list[tuple[str | None, object]]:
    result: list[tuple[str | None, object]] = []
    for message in payload.get("messages") or []:
        if not isinstance(message, dict):
            continue
        for call in message.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue
            function = call.get("function")
            if not isinstance(function, dict):
                continue
            result.append(
                (
                    function.get("name") if isinstance(function.get("name"), str) else None,
                    _arguments(function.get("arguments")),
                )
            )
    return result


def _gemini_inputs(payload: dict[str, Any]) -> list[tuple[str | None, object]]:
    result: list[tuple[str | None, object]] = []
    for content in payload.get("contents") or []:
        if not isinstance(content, dict):
            continue
        for part in content.get("parts") or []:
            if not isinstance(part, dict):
                continue
            call = part.get("functionCall")
            if isinstance(call, dict):
                result.append(
                    (
                        call.get("name") if isinstance(call.get("name"), str) else None,
                        call.get("args"),
                    )
                )
    return result


def _arguments(value: object) -> object:
    if isinstance(value, str):
        try:
            return orjson.loads(value)
        except (orjson.JSONDecodeError, TypeError):
            return None
    return value


def _path_of(arguments: dict[str, Any]) -> str | None:
    for key in _PATH_KEYS:
        value = arguments.get(key)
        if isinstance(value, str) and value:
            return value
    return None


__all__ = ["edit_observations"]
