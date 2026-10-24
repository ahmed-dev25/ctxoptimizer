"""Provider adapter protocol and shared payload helpers (SPEC section 11)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Protocol

from ctxproxy.analysis.segments import Segment
from ctxproxy.models import Provider, ToolResultRef


class ProviderAdapter(Protocol):
    provider: Provider

    def model_of(self, payload: dict[str, Any]) -> str | None: ...

    def is_stream(self, payload: dict[str, Any]) -> bool: ...

    def is_transformable(self, payload: dict[str, Any]) -> bool: ...

    def iter_tool_results(self, payload: dict[str, Any]) -> Iterator[ToolResultRef]: ...

    def segments(self, payload: dict[str, Any]) -> list[Segment]: ...

    def system_text(self, payload: dict[str, Any]) -> str: ...

    def first_user_text(self, payload: dict[str, Any]) -> str: ...

    def tool_names(self, payload: dict[str, Any]) -> list[str]: ...


class DictToolResultRef(ToolResultRef):
    """Edits a text-bearing ``content``/``output`` field inside a JSON block."""

    __slots__ = ("_block", "_key")

    def __init__(
        self,
        block: dict[str, Any],
        *,
        message_index: int,
        block_index: int | None,
        tool_use_id: str,
        tool_name: str | None,
        is_error: bool,
        key: str,
    ) -> None:
        super().__init__(
            message_index=message_index,
            block_index=block_index,
            tool_use_id=tool_use_id,
            tool_name=tool_name,
            is_error=is_error,
        )
        self._block = block
        self._key = key

    def get_text(self) -> str | None:
        return content_text(self._block.get(self._key))

    def set_text(self, new_text: str) -> None:
        set_content_text(self._block, self._key, new_text)


def content_text(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = [
            part.get("text", "")
            for part in value
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        return "".join(parts)
    return None


def set_content_text(block: dict[str, Any], key: str, text: str) -> None:
    value = block.get(key)
    if isinstance(value, list):
        remaining = [
            part for part in value if not (isinstance(part, dict) and part.get("type") == "text")
        ]
        block[key] = [{"type": "text", "text": text}, *remaining]
    else:
        block[key] = text


def blocks_of(content: Any) -> list[dict[str, Any]]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        return [block for block in content if isinstance(block, dict)]
    return []


def text_of(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(
            part.get("text", "")
            for part in value
            if isinstance(part, dict) and part.get("type") == "text"
        )
    return ""


class PassthroughAdapter:
    """No structural access; used for native Gemini/Ollama until P6."""

    provider: Provider

    def __init__(self, provider: Provider) -> None:
        self.provider = provider

    def model_of(self, payload: dict[str, Any]) -> str | None:
        model = payload.get("model")
        return model if isinstance(model, str) else None

    def is_stream(self, payload: dict[str, Any]) -> bool:
        return bool(payload.get("stream"))

    def is_transformable(self, payload: dict[str, Any]) -> bool:
        return False

    def iter_tool_results(self, payload: dict[str, Any]) -> Iterator[ToolResultRef]:
        return iter(())

    def segments(self, payload: dict[str, Any]) -> list[Segment]:
        return []

    def system_text(self, payload: dict[str, Any]) -> str:
        return ""

    def first_user_text(self, payload: dict[str, Any]) -> str:
        return ""

    def tool_names(self, payload: dict[str, Any]) -> list[str]:
        return []


__all__ = [
    "DictToolResultRef",
    "PassthroughAdapter",
    "ProviderAdapter",
    "blocks_of",
    "content_text",
    "set_content_text",
    "text_of",
]
