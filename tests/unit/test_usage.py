"""Usage parsers and SSE framing (SPEC section 14.1, provider-notes)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ctxproxy.models import Endpoint, Provider
from ctxproxy.profiles import BUILTIN_PROFILES
from ctxproxy.telemetry.sse import SSEDecoder, SSEFrameError
from ctxproxy.telemetry.usage import new_usage_parser, parse_usage_body

FIXTURES = Path(__file__).parents[1] / "fixtures"


def _feed(parser, data: bytes, chunk_size: int = 1) -> None:
    for start in range(0, len(data), chunk_size):
        parser.feed(data[start : start + chunk_size])


def _fixture(*parts: str) -> bytes:
    return FIXTURES.joinpath(*parts).read_bytes()


def test_anthropic_stream_usage() -> None:
    parser = new_usage_parser(Provider.ANTHROPIC, Endpoint.MESSAGES, BUILTIN_PROFILES["anthropic"])
    _feed(parser, _fixture("anthropic", "messages_stream.sse"), 1)
    usage = parser.result()
    assert usage.source == "provider"
    assert usage.fresh_input == 25
    assert usage.output == 15
    assert usage.cache_read is None


def test_anthropic_cumulative_delta_wins_and_ttl_breakdown() -> None:
    parser = new_usage_parser(Provider.ANTHROPIC, Endpoint.MESSAGES, BUILTIN_PROFILES["anthropic"])
    _feed(parser, _fixture("anthropic", "messages_stream_cached.sse"), 7)
    usage = parser.result()
    assert usage.fresh_input == 60
    assert usage.cache_read == 2000
    assert usage.cache_write_5m == 600
    assert usage.cache_write_1h == 400
    assert usage.output == 120
    assert usage.reasoning == 30


def test_anthropic_non_stream_body() -> None:
    usage = parse_usage_body(
        Provider.ANTHROPIC,
        Endpoint.MESSAGES,
        BUILTIN_PROFILES["anthropic"],
        _fixture("anthropic", "messages.json"),
    )
    assert usage.source == "provider"
    assert usage.fresh_input == 12
    assert usage.cache_read == 200
    assert usage.cache_write_5m == 100
    assert usage.output == 7
    assert usage.reasoning == 3


def test_openai_chat_stream_usage() -> None:
    parser = new_usage_parser(Provider.OPENAI, Endpoint.CHAT, BUILTIN_PROFILES["openai"])
    _feed(parser, _fixture("openai", "chat_stream_usage.sse"), 3)
    usage = parser.result()
    assert usage.source == "provider"
    assert usage.fresh_input == 50
    assert usage.cache_read == 40
    assert usage.cache_write_30m == 10
    assert usage.output == 20
    assert usage.reasoning == 5


def test_openai_chat_without_usage_is_estimated() -> None:
    parser = new_usage_parser(Provider.OPENAI, Endpoint.CHAT, BUILTIN_PROFILES["openai"])
    _feed(parser, _fixture("openai", "chat_stream_no_usage.sse"), 5)
    usage = parser.result()
    assert usage.source == "estimated"
    assert usage.output is not None and usage.output >= 1


def test_openai_chat_non_stream_body() -> None:
    usage = parse_usage_body(
        Provider.OPENAI,
        Endpoint.CHAT,
        BUILTIN_PROFILES["openai"],
        _fixture("openai", "chat.json"),
    )
    assert usage.fresh_input == 50
    assert usage.cache_read == 30
    assert usage.output == 10
    assert usage.reasoning == 2


def test_openai_responses_stream_usage() -> None:
    parser = new_usage_parser(Provider.OPENAI, Endpoint.RESPONSES, BUILTIN_PROFILES["openai"])
    _feed(parser, _fixture("openai", "responses_stream.sse"), 2)
    usage = parser.result()
    assert usage.source == "provider"
    assert usage.fresh_input == 130
    assert usage.cache_read == 50
    assert usage.cache_write_30m == 20
    assert usage.output == 30
    assert usage.reasoning == 10


def test_openai_responses_non_stream_ttl_breakdown() -> None:
    usage = parse_usage_body(
        Provider.OPENAI,
        Endpoint.RESPONSES,
        BUILTIN_PROFILES["openai"],
        _fixture("openai", "responses.json"),
    )
    assert usage.fresh_input == 150
    assert usage.cache_read == 100
    assert usage.cache_write_30m == 20
    assert usage.cache_write_12h == 30
    assert usage.output == 40
    assert usage.reasoning == 12


def test_deepseek_cache_fields() -> None:
    parser = new_usage_parser(Provider.OPENAI, Endpoint.CHAT, BUILTIN_PROFILES["deepseek"])
    _feed(parser, _fixture("deepseek", "chat_stream_usage.sse"), 4)
    usage = parser.result()
    assert usage.fresh_input == 40
    assert usage.cache_read == 60
    assert usage.output == 10
    assert usage.cache_write_30m == 0


def test_openrouter_reports_cost() -> None:
    parser = new_usage_parser(Provider.OPENAI, Endpoint.CHAT, BUILTIN_PROFILES["openrouter"])
    _feed(parser, _fixture("openrouter", "chat_stream_usage.sse"), 6)
    usage = parser.result()
    assert usage.fresh_input == 44
    assert usage.cache_read == 50
    assert usage.cache_write_30m == 100
    assert usage.output == 2
    assert usage.provider_cost_usd == pytest.approx(0.00042)


def test_sse_comments_crlf_and_bom() -> None:
    decoder = SSEDecoder()
    events = decoder.feed(
        b'\xef\xbb\xbf: OPENROUTER PROCESSING\r\nevent: response.created\r\ndata: {"a":1}\r\n\r\n'
    )
    assert len(events) == 1
    assert events[0].event == "response.created"
    assert events[0].data == '{"a":1}'


def test_sse_multi_line_data() -> None:
    decoder = SSEDecoder()
    assert decoder.feed(b"data: one\ndata: two\n\n")[0].data == "one\ntwo"


def test_sse_split_utf8_across_chunks() -> None:
    payload = 'data: {"text":"héllo"}\n\n'.encode()
    decoder = SSEDecoder()
    events = []
    for byte in payload:
        events.extend(decoder.feed(bytes([byte])))
    assert len(events) == 1
    assert events[0].data == '{"text":"héllo"}'


def test_sse_oversized_line_is_rejected() -> None:
    decoder = SSEDecoder(max_line_bytes=8)
    with pytest.raises(SSEFrameError):
        decoder.feed(b"data: " + b"a" * 32)


def test_garbage_never_raises() -> None:
    parser = new_usage_parser(Provider.ANTHROPIC, Endpoint.MESSAGES, BUILTIN_PROFILES["anthropic"])
    parser.feed(b"\xff\x00not an event")
    usage = parser.result()
    assert usage.source in {"provider", "estimated", "none"}


def test_gemini_native_stream_usage() -> None:
    parser = new_usage_parser(Provider.GEMINI, Endpoint.GENERATE, BUILTIN_PROFILES["gemini"])
    data = (
        b'data: {"candidates":[{"content":{"parts":[{"text":"hi"}]}}],'
        b'"usageMetadata":{"promptTokenCount":100,"cachedContentTokenCount":40,'
        b'"candidatesTokenCount":20,"thoughtsTokenCount":5}}\n\n'
    )
    _feed(parser, data, 3)
    usage = parser.result()
    assert usage.source == "provider"
    assert usage.fresh_input == 60
    assert usage.cache_read == 40
    assert usage.output == 20
    assert usage.reasoning == 5


def test_gemini_native_non_stream_body() -> None:
    body = (
        b'{"usageMetadata":{"promptTokenCount":30,"cachedContentTokenCount":10,'
        b'"candidatesTokenCount":7}}'
    )
    usage = parse_usage_body(Provider.GEMINI, Endpoint.GENERATE, BUILTIN_PROFILES["gemini"], body)
    assert usage.source == "provider"
    assert usage.fresh_input == 20
    assert usage.cache_read == 10
    assert usage.output == 7


def test_ollama_stream_usage_is_ndjson() -> None:
    parser = new_usage_parser(Provider.OLLAMA, Endpoint.CHAT, BUILTIN_PROFILES["ollama"])
    data = (
        b'{"message":{"content":"hi"},"done":false}\n'
        b'{"prompt_eval_count":100,"prompt_eval_cached_count":40,'
        b'"eval_count":20,"done":true}\n'
    )
    _feed(parser, data, 5)
    usage = parser.result()
    assert usage.source == "provider"
    assert usage.fresh_input == 60
    assert usage.cache_read == 40
    assert usage.output == 20


def test_ollama_non_stream_body() -> None:
    usage = parse_usage_body(
        Provider.OLLAMA,
        Endpoint.CHAT,
        BUILTIN_PROFILES["ollama"],
        b'{"prompt_eval_count":12,"eval_count":4,"done":true}',
    )
    assert usage.source == "provider"
    assert usage.fresh_input == 12
    assert usage.output == 4
