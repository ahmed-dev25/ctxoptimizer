"""OpenAI Responses adapter (SPEC section 11.3)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from ctxproxy.analysis.segments import Segment, make_segment
from ctxproxy.models import Provider, ToolResultRef
from ctxproxy.providers.base import DictToolResultRef, blocks_of, text_of


class OpenAIResponsesAdapter:
    provider = Provider.OPENAI

    def model_of(self, payload: dict[str, Any]) -> str | None:
        model = payload.get("model")
        return model if isinstance(model, str) else None

    def is_stream(self, payload: dict[str, Any]) -> bool:
        return bool(payload.get("stream"))

    def is_transformable(self, payload: dict[str, Any]) -> bool:
        return not bool(payload.get("previous_response_id"))

    def iter_tool_results(self, payload: dict[str, Any]) -> Iterator[ToolResultRef]:
        names = self._call_names(payload)
        for message_index, item in enumerate(self._input_items(payload)):
            if not isinstance(item, dict) or item.get("type") != "function_call_output":
                continue
            call_id = str(item.get("call_id") or "")
            yield DictToolResultRef(
                item,
                message_index=message_index,
                block_index=None,
                tool_use_id=call_id,
                tool_name=names.get(call_id),
                is_error=False,
                key="output",
            )

    def segments(self, payload: dict[str, Any]) -> list[Segment]:
        result: list[Segment] = []
        instructions = payload.get("instructions")
        if isinstance(instructions, str) and instructions:
            result.append(
                make_segment(
                    "system",
                    {"type": "text", "text": instructions},
                    block_index=0,
                )
            )
        for index, tool in enumerate(payload.get("tools") or []):
            if isinstance(tool, dict):
                result.append(make_segment("tool_def", tool, block_index=index))
        for message_index, item in enumerate(self._input_items(payload)):
            if not isinstance(item, dict):
                continue
            if item.get("type") in {"message", None} and item.get("role"):
                role = str(item["role"])
                content = item.get("content")
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
                for block_index, block in enumerate(blocks_of(content)):
                    result.append(
                        make_segment(
                            "message",
                            {"role": role, **block},
                            msg_index=message_index,
                            block_index=block_index,
                        )
                    )
            else:
                result.append(make_segment("message", item, msg_index=message_index))
        return result

    def system_text(self, payload: dict[str, Any]) -> str:
        return payload["instructions"] if isinstance(payload.get("instructions"), str) else ""

    def first_user_text(self, payload: dict[str, Any]) -> str:
        for item in self._input_items(payload):
            if isinstance(item, dict) and item.get("role") == "user":
                return text_of(item.get("content"))
        return ""

    def tool_names(self, payload: dict[str, Any]) -> list[str]:
        return [
            str(tool["name"])
            for tool in payload.get("tools") or []
            if isinstance(tool, dict) and isinstance(tool.get("name"), str)
        ]

    def _input_items(self, payload: dict[str, Any]) -> list[Any]:
        value = payload.get("input")
        if isinstance(value, str):
            return [{"type": "message", "role": "user", "content": value}]
        return value if isinstance(value, list) else []

    def _call_names(self, payload: dict[str, Any]) -> dict[str, str]:
        names: dict[str, str] = {}
        for item in self._input_items(payload):
            if isinstance(item, dict) and item.get("type") == "function_call":
                call_id = item.get("call_id")
                name = item.get("name")
                if isinstance(call_id, str) and isinstance(name, str):
                    names[call_id] = name
        return names


__all__ = ["OpenAIResponsesAdapter"]
