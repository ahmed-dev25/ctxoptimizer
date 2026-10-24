"""Anthropic Messages adapter (SPEC section 11.1)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from ctxproxy.analysis.segments import Segment, make_segment
from ctxproxy.models import Provider, ToolResultRef
from ctxproxy.providers.base import (
    DictToolResultRef,
    blocks_of,
    text_of,
)


class AnthropicAdapter:
    provider = Provider.ANTHROPIC

    def model_of(self, payload: dict[str, Any]) -> str | None:
        model = payload.get("model")
        return model if isinstance(model, str) else None

    def is_stream(self, payload: dict[str, Any]) -> bool:
        return bool(payload.get("stream"))

    def is_transformable(self, payload: dict[str, Any]) -> bool:
        return True

    def iter_tool_results(self, payload: dict[str, Any]) -> Iterator[ToolResultRef]:
        names = self._tool_use_names(payload)
        for message_index, message in enumerate(payload.get("messages") or []):
            if not isinstance(message, dict):
                continue
            for block_index, block in enumerate(blocks_of(message.get("content"))):
                if block.get("type") != "tool_result":
                    continue
                tool_use_id = str(block.get("tool_use_id") or "")
                yield DictToolResultRef(
                    block,
                    message_index=message_index,
                    block_index=block_index,
                    tool_use_id=tool_use_id,
                    tool_name=names.get(tool_use_id),
                    is_error=bool(block.get("is_error")),
                    key="content",
                )

    def segments(self, payload: dict[str, Any]) -> list[Segment]:
        result: list[Segment] = []
        for index, tool in enumerate(payload.get("tools") or []):
            if isinstance(tool, dict):
                result.append(make_segment("tool_def", tool, block_index=index))
        system = payload.get("system")
        system_blocks = blocks_of(system)
        if isinstance(system, str):
            system_blocks = [{"type": "text", "text": system}]
        for index, block in enumerate(system_blocks):
            result.append(make_segment("system", block, block_index=index))
        for message_index, message in enumerate(payload.get("messages") or []):
            if not isinstance(message, dict):
                continue
            role = str(message.get("role") or "")
            for block_index, block in enumerate(blocks_of(message.get("content"))):
                result.append(
                    make_segment(
                        "message",
                        {**block, "role": role},
                        msg_index=message_index,
                        block_index=block_index,
                    )
                )
        return result

    def system_text(self, payload: dict[str, Any]) -> str:
        return text_of(payload.get("system"))

    def first_user_text(self, payload: dict[str, Any]) -> str:
        for message in payload.get("messages") or []:
            if isinstance(message, dict) and message.get("role") == "user":
                return text_of(message.get("content"))
        return ""

    def tool_names(self, payload: dict[str, Any]) -> list[str]:
        return [
            str(tool["name"])
            for tool in payload.get("tools") or []
            if isinstance(tool, dict) and isinstance(tool.get("name"), str)
        ]

    def used_tool_names(self, payload: dict[str, Any]) -> list[str]:
        return list(self._tool_use_names(payload).values())

    def _tool_use_names(self, payload: dict[str, Any]) -> dict[str, str]:
        names: dict[str, str] = {}
        for message in payload.get("messages") or []:
            if not isinstance(message, dict):
                continue
            for block in blocks_of(message.get("content")):
                if block.get("type") == "tool_use" and isinstance(block.get("id"), str):
                    names[block["id"]] = str(block.get("name") or "")
        return names


__all__ = ["AnthropicAdapter"]
