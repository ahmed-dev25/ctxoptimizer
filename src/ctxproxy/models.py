"""Core dataclasses and enums (SPEC section 10).

These are the provider-agnostic shapes every layer passes around. Payload
mutation stays behind :class:`ToolResultRef`, so transforms never need to know
a provider's JSON layout (INV-7).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from ctxproxy.config import Config


class Provider(StrEnum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GEMINI = "gemini"
    OLLAMA = "ollama"


class Endpoint(StrEnum):
    MESSAGES = "messages"
    CHAT = "chat"
    RESPONSES = "responses"
    GENERATE = "generate"
    PASSTHROUGH = "passthrough"


class Mode(StrEnum):
    PASSTHROUGH = "passthrough"
    SHADOW = "shadow"
    ACTIVE = "active"


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Everything the pipeline needs about one request, frozen at ingress."""

    request_id: str
    provider: Provider
    endpoint: Endpoint
    upstream_name: str
    model: str | None
    stream: bool
    mode: Mode
    session_id: str
    project: str | None
    client_name: str | None
    config: Config
    config_hash: str
    started_monotonic: float


@dataclass(slots=True)
class ToolResultRef:
    """Mutable handle to one tool-result text block (INV-7: text only).

    Adapters implement :meth:`get_text` and :meth:`set_text` for their payload
    shape. Everything downstream treats the block as an opaque string.
    """

    message_index: int
    block_index: int | None
    tool_use_id: str
    tool_name: str | None
    is_error: bool

    def get_text(self) -> str | None:
        """Return the text, or None when the block is not text."""
        raise NotImplementedError

    def set_text(self, new_text: str) -> None:
        """Replace the block text in place."""
        raise NotImplementedError


@dataclass(slots=True)
class TransformReport:
    """Outcome of one transform run, persisted per request."""

    transform_id: str
    ran: bool = False
    changed: bool = False
    items_touched: int = 0
    bytes_before: int = 0
    bytes_after: int = 0
    est_tokens_before: int = 0
    est_tokens_after: int = 0
    duration_ms: float = 0.0
    discarded_reason: str | None = None
    error: str | None = None
    notes: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class Usage:
    """Normalized provider usage (SPEC section 14.1)."""

    fresh_input: int | None = None
    cache_read: int | None = None
    cache_write_5m: int | None = None
    cache_write_1h: int | None = None
    output: int | None = None
    reasoning: int | None = None
    source: Literal["provider", "estimated", "none"] = "none"
    raw: dict[str, object] | None = None
    assistant_text_hashes: list[bytes] | None = None


@dataclass(slots=True)
class WasteFinding:
    """An advisory, evidence-linked waste finding (INV-16, INV-18)."""

    finding_id: str
    ts: float
    session_id: str
    project: str | None
    detector: str
    key_hash: bytes
    request_id: str | None
    occurrences: int
    first_seen_ts: float
    last_seen_ts: float
    evidence: dict[str, object]
    est_tokens_wasted: int | None
    est_cost_usd: float | None
    status: Literal["new", "ack", "fixed", "skipped"] = "new"


__all__ = [
    "Endpoint",
    "Mode",
    "Provider",
    "RequestContext",
    "ToolResultRef",
    "TransformReport",
    "Usage",
    "WasteFinding",
]
