"""Incremental usage parsers for Anthropic, OpenAI Chat and OpenAI Responses.

The parsers are fed raw upstream bytes. ``feed`` never raises: a malformed stream
disables the parser and leaves whatever was already parsed (INV-3). Normalization
follows SPEC section 14.1 plus the corrections in ``docs/provider-notes.md``.
"""

from __future__ import annotations

import math
from typing import Any, Protocol

import orjson

from ctxoptimizer.models import Endpoint, Provider, Usage
from ctxoptimizer.profiles import UpstreamProfile
from ctxoptimizer.telemetry.sse import SSEDecoder, SSEEvent

_CHAT_STYLES = frozenset({"openai", "deepseek", "openrouter", "gemini-openai", "ollama-openai"})


class UsageParser(Protocol):
    """Side-channel parser fed raw upstream bytes; never raises outward."""

    def feed(self, chunk: bytes) -> None: ...

    def disable(self) -> None: ...

    def result(self) -> Usage: ...


class NullUsageParser:
    """Records that usage is unavailable, without inspecting the stream."""

    def __init__(self) -> None:
        self._disabled = False

    def feed(self, chunk: bytes) -> None:
        return

    def disable(self) -> None:
        self._disabled = True

    @property
    def disabled(self) -> bool:
        return self._disabled

    def result(self) -> Usage:
        return Usage(source="none")


class _BaseParser:
    def __init__(self) -> None:
        self._decoder = SSEDecoder()
        self._disabled = False
        self._usage = Usage(source="none")
        self._output_chars = 0

    def feed(self, chunk: bytes) -> None:
        if self._disabled:
            return
        try:
            for event in self._decoder.feed(chunk):
                self._handle(event)
        except Exception:
            self.disable()

    def disable(self) -> None:
        self._disabled = True

    def result(self) -> Usage:
        if self._usage.source != "provider" and self._output_chars:
            self._usage.output = max(1, math.ceil(self._output_chars / 3.5))
            self._usage.source = "estimated"
        return self._usage

    def _handle(self, event: SSEEvent) -> None:
        raise NotImplementedError


class AnthropicUsageParser(_BaseParser):
    """Anthropic sends full usage at message_start and cumulative at message_delta."""

    def __init__(self) -> None:
        super().__init__()
        self._fields: dict[str, Any] = {}
        self._cache_creation: dict[str, Any] | None = None

    def _handle(self, event: SSEEvent) -> None:
        payload = _json(event.data)
        if payload is None:
            return
        kind = payload.get("type") or event.event
        if kind == "message_start":
            message = _dict(payload.get("message"))
            usage = message.get("usage")
            if isinstance(usage, dict):
                self._merge(usage)
        elif kind == "message_delta":
            usage = payload.get("usage")
            if isinstance(usage, dict):
                self._merge(usage)
        elif kind == "content_block_delta":
            delta = _dict(payload.get("delta"))
            if delta.get("type") == "text_delta":
                self._output_chars += len(_text(delta.get("text")))
            elif delta.get("type") == "thinking_delta":
                self._output_chars += len(_text(delta.get("thinking")))

    def _merge(self, usage: dict[str, Any]) -> None:
        for key in (
            "input_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
            "output_tokens",
        ):
            value = usage.get(key)
            if value is not None:
                self._fields[key] = value
        details = usage.get("output_tokens_details")
        if isinstance(details, dict):
            self._fields["output_tokens_details"] = details
        cache_creation = usage.get("cache_creation")
        if isinstance(cache_creation, dict):
            self._cache_creation = cache_creation
        self._usage = _anthropic_usage(self._fields, self._cache_creation)


class OpenAIChatUsageParser(_BaseParser):
    """Chat Completions usage arrives in the final chunk when requested."""

    def __init__(self, style: str = "openai") -> None:
        super().__init__()
        self._style = style

    def _handle(self, event: SSEEvent) -> None:
        data = event.data.strip()
        if not data or data == "[DONE]":
            return
        payload = _json(data)
        if payload is None:
            return
        usage = payload.get("usage")
        if isinstance(usage, dict):
            self._usage = _chat_usage(usage, self._style)
        for choice in payload.get("choices") or []:
            if not isinstance(choice, dict):
                continue
            delta = _dict(choice.get("delta"))
            self._output_chars += len(_text(delta.get("content")))
            self._output_chars += len(_text(delta.get("reasoning_content")))


class OpenAIResponsesUsageParser(_BaseParser):
    """Responses reports true usage on the final Response object."""

    def _handle(self, event: SSEEvent) -> None:
        payload = _json(event.data)
        if payload is None:
            return
        kind = payload.get("type") or event.event
        if kind in {"response.completed", "response.incomplete", "response.failed"}:
            response = _dict(payload.get("response"))
            usage = response.get("usage")
            if isinstance(usage, dict):
                self._usage = _responses_usage(usage)
        elif kind == "response.output_text.delta":
            self._output_chars += len(_text(payload.get("delta")))


class GeminiUsageParser(_BaseParser):
    """Native Gemini streams usage in ``usageMetadata`` (often on every chunk)."""

    def _handle(self, event: SSEEvent) -> None:
        payload = _json(event.data)
        if payload is None:
            return
        raw = payload.get("usageMetadata")
        if isinstance(raw, dict):
            self._usage = _gemini_usage(raw)
        for candidate in payload.get("candidates") or []:
            if not isinstance(candidate, dict):
                continue
            content = _dict(candidate.get("content"))
            for part in content.get("parts") or []:
                if isinstance(part, dict):
                    self._output_chars += len(_text(part.get("text")))


class OllamaUsageParser:
    """Ollama speaks newline-delimited JSON, not SSE."""

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._disabled = False
        self._usage = Usage(source="none")
        self._output_chars = 0

    def feed(self, chunk: bytes) -> None:
        if self._disabled:
            return
        self._buffer.extend(chunk)
        while True:
            index = self._buffer.find(b"\n")
            if index < 0:
                break
            line = bytes(self._buffer[:index])
            del self._buffer[: index + 1]
            self._handle_line(line)

    def disable(self) -> None:
        self._disabled = True

    def result(self) -> Usage:
        if self._buffer:
            self._handle_line(bytes(self._buffer))
            self._buffer.clear()
        if self._usage.source != "provider" and self._output_chars:
            self._usage.output = max(1, math.ceil(self._output_chars / 3.5))
            self._usage.source = "estimated"
        return self._usage

    def _handle_line(self, line: bytes) -> None:
        if not line.strip():
            return
        try:
            payload = orjson.loads(line)
        except (orjson.JSONDecodeError, TypeError):
            self.disable()
            return
        if not isinstance(payload, dict):
            return
        message = _dict(payload.get("message"))
        self._output_chars += len(_text(message.get("content")))
        self._output_chars += len(_text(payload.get("response")))
        if "prompt_eval_count" in payload or "eval_count" in payload:
            self._usage = _ollama_usage(payload)


def new_usage_parser(
    provider: Provider, endpoint: Endpoint, profile: UpstreamProfile
) -> UsageParser:
    """Select the parser for one request from its endpoint and profile."""
    if endpoint is Endpoint.RESPONSES:
        return OpenAIResponsesUsageParser()
    if profile.usage == "anthropic":
        return AnthropicUsageParser()
    if profile.usage == "gemini":
        return GeminiUsageParser()
    if profile.usage == "ollama":
        return OllamaUsageParser()
    if profile.usage in _CHAT_STYLES:
        return OpenAIChatUsageParser(profile.usage)
    return NullUsageParser()


def parse_usage_body(
    provider: Provider, endpoint: Endpoint, profile: UpstreamProfile, body: bytes
) -> Usage:
    """Parse a non-streaming response body."""
    try:
        payload = orjson.loads(body)
    except (orjson.JSONDecodeError, TypeError):
        return Usage(source="none")
    if not isinstance(payload, dict):
        return Usage(source="none")
    if endpoint is Endpoint.RESPONSES:
        usage = payload.get("usage")
        return _responses_usage(usage) if isinstance(usage, dict) else Usage(source="none")
    if profile.usage == "gemini":
        usage = payload.get("usageMetadata")
        return _gemini_usage(usage) if isinstance(usage, dict) else Usage(source="none")
    if profile.usage == "ollama":
        return _ollama_usage(payload)
    if profile.usage == "anthropic":
        usage = payload.get("usage")
        if not isinstance(usage, dict):
            return Usage(source="none")
        cache_creation = usage.get("cache_creation")
        return _anthropic_usage(usage, cache_creation if isinstance(cache_creation, dict) else None)
    if profile.usage in _CHAT_STYLES:
        usage = payload.get("usage")
        return (
            _chat_usage(usage, profile.usage) if isinstance(usage, dict) else Usage(source="none")
        )
    return Usage(source="none")


def _anthropic_usage(raw: dict[str, Any], cache_creation: dict[str, Any] | None) -> Usage:
    write_5m = _int(_dict(cache_creation).get("ephemeral_5m_input_tokens"))
    write_1h = _int(_dict(cache_creation).get("ephemeral_1h_input_tokens"))
    total_write = _int(raw.get("cache_creation_input_tokens"))
    if write_5m is None and write_1h is None and total_write:
        write_5m = total_write
    details = _dict(raw.get("output_tokens_details"))
    raw_out: dict[str, object] = dict(raw)
    if cache_creation:
        raw_out["cache_creation"] = cache_creation
    return Usage(
        fresh_input=_int(raw.get("input_tokens")),
        cache_read=_int(raw.get("cache_read_input_tokens")),
        cache_write_5m=write_5m,
        cache_write_1h=write_1h,
        output=_int(raw.get("output_tokens")),
        reasoning=_int(details.get("thinking_tokens")),
        source="provider",
        raw=raw_out,
    )


def _gemini_usage(raw: dict[str, Any]) -> Usage:
    prompt = _int(raw.get("promptTokenCount")) or 0
    cached = _int(raw.get("cachedContentTokenCount")) or 0
    return Usage(
        fresh_input=max(prompt - cached, 0),
        cache_read=cached,
        output=_int(raw.get("candidatesTokenCount")) or 0,
        reasoning=_int(raw.get("thoughtsTokenCount")),
        source="provider",
        raw=dict(raw),
    )


def _ollama_usage(raw: dict[str, Any]) -> Usage:
    prompt = _int(raw.get("prompt_eval_count"))
    output = _int(raw.get("eval_count"))
    if prompt is None and output is None:
        return Usage(source="none")
    cached = _int(raw.get("prompt_eval_cached_count"))
    cached_tokens = cached or 0
    return Usage(
        fresh_input=max((prompt or 0) - cached_tokens, 0),
        cache_read=cached_tokens if cached is not None else None,
        output=output,
        source="provider",
        raw=dict(raw),
    )


def _chat_usage(raw: dict[str, Any], style: str) -> Usage:
    prompt = _int(raw.get("prompt_tokens")) or 0
    details = _dict(raw.get("prompt_tokens_details"))
    cached = _int(details.get("cached_tokens")) or 0
    written = _int(details.get("cache_write_tokens")) or 0
    hit = _int(raw.get("prompt_cache_hit_tokens"))
    miss = _int(raw.get("prompt_cache_miss_tokens"))
    if hit is not None or miss is not None:
        cached = hit or 0
        fresh = miss if miss is not None else max(prompt - cached - written, 0)
    else:
        fresh = max(prompt - cached - written, 0)
    completion_details = _dict(raw.get("completion_tokens_details"))
    return Usage(
        fresh_input=fresh,
        cache_read=cached,
        cache_write_30m=written,
        output=_int(raw.get("completion_tokens")) or 0,
        reasoning=_int(completion_details.get("reasoning_tokens")),
        provider_cost_usd=_float(raw.get("cost")),
        source="provider",
        raw=dict(raw),
    )


def _responses_usage(raw: dict[str, Any]) -> Usage:
    input_tokens = _int(raw.get("input_tokens")) or 0
    details = _dict(raw.get("input_tokens_details"))
    cached = _int(details.get("cached_tokens")) or 0
    written = _int(details.get("cache_write_tokens")) or 0
    write_details = _dict(details.get("cache_write_tokens_details"))
    write_30m = _int(write_details.get("ttl_30m_tokens"))
    write_12h = _int(write_details.get("ttl_12h_tokens"))
    if write_30m is None and write_12h is None:
        write_30m = written
    output_details = _dict(raw.get("output_tokens_details"))
    return Usage(
        fresh_input=max(input_tokens - cached - written, 0),
        cache_read=cached,
        cache_write_30m=write_30m,
        cache_write_12h=write_12h,
        output=_int(raw.get("output_tokens")) or 0,
        reasoning=_int(output_details.get("reasoning_tokens")),
        provider_cost_usd=_float(raw.get("cost")),
        source="provider",
        raw=dict(raw),
    )


def _json(data: str) -> dict[str, Any] | None:
    if not data:
        return None
    try:
        value = orjson.loads(data)
    except (orjson.JSONDecodeError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


__all__ = [
    "AnthropicUsageParser",
    "GeminiUsageParser",
    "NullUsageParser",
    "OllamaUsageParser",
    "OpenAIChatUsageParser",
    "OpenAIResponsesUsageParser",
    "UsageParser",
    "new_usage_parser",
    "parse_usage_body",
]
