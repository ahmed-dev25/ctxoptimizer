"""OpenAI Chat Completions adapter (SPEC section 11.2)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from ctxproxy.analysis.segments import Segment, make_segment
from ctxproxy.models import Provider, ToolResultRef
from ctxproxy.providers.base import DictToolResultRef, blocks_of, text_of


class OpenAIChatAdapter:
    provider = Provider.OPENAI

    def model_of(self, payload: dict[str, Any]) -> str | None:
        model = payload.get("model")
        return model if isinstance(model, str) else None

    def is_stream(self, payload: dict[str, Any]) -> bool:
        return bool(payload.get("stream"))

    def is_transformable(self, payload: dict[str, Any]) -> bool:
        return True

    def iter_tool_results(self, payload: dict[str, Any]) -> Iterator[ToolResultRef]:
        names = self._tool_call_names(payload)
        for message_index, message in enumerate(payload.get("messages") or []):
            if not isinstance(message, dict) or message.get("role") != "tool":
                continue
            call_id = str(message.get("tool_call_id") or "")
            yield DictToolResultRef(
                message,
                message_index=message_index,
                block_index=None,
                tool_use_id=call_id,
                tool_name=names.get(call_id),
                is_error=False,
                key="content",
            )

    def segments(self, payload: dict[str, Any]) -> list[Segment]:
        result: list[Segment] = []
        for index, tool in enumerate(payload.get("tools") or []):
            if isinstance(tool, dict):
                result.append(make_segment("tool_def", tool, block_index=index))
        for message_index, message in enumerate(payload.get("messages") or []):
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
                continue
            if content is None:
                tool_calls = message.get("tool_calls")
                if isinstance(tool_calls, list) and tool_calls:
                    result.append(
                        make_segment(
                            "message",
                            {"role": role, "tool_calls": tool_calls},
                            msg_index=message_index,
                        )
                    )
                continue
            for block_index, block in enumerate(blocks_of(content)):
                result.append(
                    make_segment(
                        "message",
                        {"role": role, **block},
                        msg_index=message_index,
                        block_index=block_index,
                    )
                )
        return result

    def system_text(self, payload: dict[str, Any]) -> str:
        parts = [
            text_of(message.get("content"))
            for message in payload.get("messages") or []
            if isinstance(message, dict) and message.get("role") in {"system", "developer"}
        ]
        return "\n".join(part for part in parts if part)

    def first_user_text(self, payload: dict[str, Any]) -> str:
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

    def _tool_call_names(self, payload: dict[str, Any]) -> dict[str, str]:
        names: dict[str, str] = {}
        for message in payload.get("messages") or []:
            if not isinstance(message, dict):
                continue
            for call in message.get("tool_calls") or []:
                if not isinstance(call, dict):
                    continue
                function = call.get("function")
                if isinstance(call.get("id"), str) and isinstance(function, dict):
                    names[call["id"]] = str(function.get("name") or "")
        return names


__all__ = ["OpenAIChatAdapter"]
