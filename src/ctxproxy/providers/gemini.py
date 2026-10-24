"""Native Gemini ``generateContent`` adapter (SPEC section 11.4, P6-1).

Telemetry first: segments and tool-result handles are exposed so the analysis
layer can measure usage. Transforms only touch string leaves inside
``functionResponse`` parts, which is the byte-true subset.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from ctxproxy.analysis.segments import Segment, make_segment
from ctxproxy.models import Provider, ToolResultRef
from ctxproxy.providers.base import MappingToolResultRef, text_of


class GeminiAdapter:
    provider = Provider.GEMINI

    def model_of(self, payload: dict[str, Any]) -> str | None:
        model = payload.get("model")
        return model if isinstance(model, str) else None

    def is_stream(self, payload: dict[str, Any]) -> bool:
        return bool(payload.get("stream"))

    def is_transformable(self, payload: dict[str, Any]) -> bool:
        return isinstance(payload.get("contents"), list)

    def iter_tool_results(self, payload: dict[str, Any]) -> Iterator[ToolResultRef]:
        for message_index, content in enumerate(payload.get("contents") or []):
            if not isinstance(content, dict):
                continue
            for block_index, part in enumerate(content.get("parts") or []):
                if not isinstance(part, dict):
                    continue
                response = part.get("functionResponse")
                if not isinstance(response, dict):
                    continue
                name = str(response.get("name") or "")
                handle = _response_handle(response)
                if handle is None:
                    continue
                parent, key, is_error = handle
                yield MappingToolResultRef(
                    parent,
                    key=key,
                    message_index=message_index,
                    block_index=block_index,
                    tool_use_id=name,
                    tool_name=name or None,
                    is_error=is_error,
                )

    def segments(self, payload: dict[str, Any]) -> list[Segment]:
        result: list[Segment] = []
        for tool in payload.get("tools") or []:
            if not isinstance(tool, dict):
                continue
            result.extend(
                make_segment("tool_def", declaration)
                for declaration in tool.get("functionDeclarations") or []
                if isinstance(declaration, dict)
            )
        system = _parts(payload.get("systemInstruction"))
        for index, part in enumerate(system):
            result.append(make_segment("system", part, block_index=index))
        for message_index, content in enumerate(payload.get("contents") or []):
            if not isinstance(content, dict):
                continue
            role = str(content.get("role") or "")
            for block_index, part in enumerate(content.get("parts") or []):
                if isinstance(part, dict):
                    result.append(
                        make_segment(
                            "message",
                            {"role": role, **part},
                            msg_index=message_index,
                            block_index=block_index,
                        )
                    )
        return result

    def system_text(self, payload: dict[str, Any]) -> str:
        return text_of(_parts(payload.get("systemInstruction")))

    def first_user_text(self, payload: dict[str, Any]) -> str:
        for content in payload.get("contents") or []:
            if isinstance(content, dict) and content.get("role") == "user":
                return text_of(_parts(content))
        return ""

    def tool_names(self, payload: dict[str, Any]) -> list[str]:
        names: list[str] = []
        for tool in payload.get("tools") or []:
            if not isinstance(tool, dict):
                continue
            names.extend(
                declaration["name"]
                for declaration in tool.get("functionDeclarations") or []
                if isinstance(declaration, dict) and isinstance(declaration.get("name"), str)
            )
        return names

    def used_tool_names(self, payload: dict[str, Any]) -> list[str]:
        names: list[str] = []
        for content in payload.get("contents") or []:
            if not isinstance(content, dict):
                continue
            for part in content.get("parts") or []:
                if not isinstance(part, dict):
                    continue
                call = part.get("functionCall")
                if isinstance(call, dict) and isinstance(call.get("name"), str):
                    names.append(call["name"])
        return names


def _parts(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        parts = value.get("parts")
        if isinstance(parts, list):
            return [part for part in parts if isinstance(part, dict)]
    return []


def _response_handle(
    response: dict[str, Any],
) -> tuple[dict[str, Any], str, bool] | None:
    inner = response.get("response")
    if isinstance(inner, str):
        return response, "response", False
    if not isinstance(inner, dict):
        return None
    is_error = "error" in inner
    for key in ("content", "result", "output", "text"):
        if isinstance(inner.get(key), str):
            return inner, key, is_error
    return None


__all__ = ["GeminiAdapter"]
