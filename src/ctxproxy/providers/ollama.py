"""Native Ollama ``/api/chat`` and ``/api/generate`` adapter (P6-2)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from ctxproxy.analysis.segments import Segment, make_segment
from ctxproxy.models import Provider, ToolResultRef
from ctxproxy.providers.base import DictToolResultRef, text_of


class OllamaAdapter:
    provider = Provider.OLLAMA

    def model_of(self, payload: dict[str, Any]) -> str | None:
        model = payload.get("model")
        return model if isinstance(model, str) else None

    def is_stream(self, payload: dict[str, Any]) -> bool:
        # Ollama streams by default when ``stream`` is omitted.
        return bool(payload.get("stream", True))

    def is_transformable(self, payload: dict[str, Any]) -> bool:
        return isinstance(payload.get("messages"), list) or isinstance(payload.get("prompt"), str)

    def iter_tool_results(self, payload: dict[str, Any]) -> Iterator[ToolResultRef]:
        for message_index, message in enumerate(payload.get("messages") or []):
            if not isinstance(message, dict) or message.get("role") != "tool":
                continue
            yield DictToolResultRef(
                message,
                message_index=message_index,
                block_index=None,
                tool_use_id=str(message.get("tool_name") or ""),
                tool_name=(
                    message.get("tool_name") if isinstance(message.get("tool_name"), str) else None
                ),
                is_error=False,
                key="content",
            )

    def segments(self, payload: dict[str, Any]) -> list[Segment]:
        result: list[Segment] = []
        for tool in payload.get("tools") or []:
            if not isinstance(tool, dict):
                continue
            function = tool.get("function")
            if isinstance(function, dict):
                result.append(make_segment("tool_def", function))
        system = payload.get("system")
        if isinstance(system, str) and system:
            result.append(make_segment("system", {"type": "text", "text": system}))
        messages = payload.get("messages")
        if isinstance(messages, list):
            for message_index, message in enumerate(messages):
                if not isinstance(message, dict):
                    continue
                role = str(message.get("role") or "")
                content = message.get("content")
                if isinstance(content, str):
                    result.append(
                        make_segment(
                            "message",
                            {"role": role, "content": content},
                            msg_index=message_index,
                            block_index=0,
                        )
                    )
                elif content is None and isinstance(message.get("tool_calls"), list):
                    result.append(
                        make_segment(
                            "message",
                            {"role": role, "tool_calls": message["tool_calls"]},
                            msg_index=message_index,
                        )
                    )
        elif isinstance(payload.get("prompt"), str):
            result.append(
                make_segment(
                    "message",
                    {"role": "user", "content": payload["prompt"]},
                    msg_index=0,
                    block_index=0,
                )
            )
        return result

    def system_text(self, payload: dict[str, Any]) -> str:
        system = payload.get("system")
        if isinstance(system, str):
            return system
        parts = [
            text_of(message.get("content"))
            for message in payload.get("messages") or []
            if isinstance(message, dict) and message.get("role") == "system"
        ]
        return "\n".join(part for part in parts if part)

    def first_user_text(self, payload: dict[str, Any]) -> str:
        prompt = payload.get("prompt")
        if isinstance(prompt, str):
            return prompt
        for message in payload.get("messages") or []:
            if isinstance(message, dict) and message.get("role") == "user":
                return text_of(message.get("content"))
        return ""

    def tool_names(self, payload: dict[str, Any]) -> list[str]:
        names: list[str] = []
        for tool in payload.get("tools") or []:
            if not isinstance(tool, dict):
                continue
            function = tool.get("function")
            if isinstance(function, dict) and isinstance(function.get("name"), str):
                names.append(function["name"])
        return names

    def used_tool_names(self, payload: dict[str, Any]) -> list[str]:
        names: list[str] = []
        for message in payload.get("messages") or []:
            if not isinstance(message, dict):
                continue
            for call in message.get("tool_calls") or []:
                if not isinstance(call, dict):
                    continue
                function = call.get("function")
                if isinstance(function, dict) and isinstance(function.get("name"), str):
                    names.append(function["name"])
        return names


__all__ = ["OllamaAdapter"]
