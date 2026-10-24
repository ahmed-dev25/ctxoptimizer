"""Gateway-specific usage quirks (DeepSeek, OpenRouter, Gemini-compat, Ollama)."""

from __future__ import annotations

from pathlib import Path

from ctxproxy.models import Endpoint, Provider
from ctxproxy.profiles import BUILTIN_PROFILES
from ctxproxy.telemetry.usage import new_usage_parser, parse_usage_body

FIXTURES = Path(__file__).parents[1] / "fixtures"


def _fixture(*parts: str) -> bytes:
    return FIXTURES.joinpath(*parts).read_bytes()


def _feed(parser, data: bytes, chunk_size: int = 3) -> None:
    for start in range(0, len(data), chunk_size):
        parser.feed(data[start : start + chunk_size])


def test_gemini_openai_compat_usage() -> None:
    parser = new_usage_parser(Provider.OPENAI, Endpoint.CHAT, BUILTIN_PROFILES["gemini-openai"])
    _feed(parser, _fixture("gemini", "chat_stream_usage.sse"))
    usage = parser.result()
    assert usage.source == "provider"
    assert usage.fresh_input == 40
    assert usage.cache_read == 10
    assert usage.output == 5


def test_ollama_openai_compat_without_usage_is_estimated() -> None:
    parser = new_usage_parser(Provider.OPENAI, Endpoint.CHAT, BUILTIN_PROFILES["ollama-openai"])
    _feed(parser, _fixture("ollama", "chat_stream_no_usage.sse"))
    usage = parser.result()
    assert usage.source == "estimated"
    assert usage.output is not None and usage.output >= 1


def test_deepseek_non_stream_body() -> None:
    usage = parse_usage_body(
        Provider.OPENAI,
        Endpoint.CHAT,
        BUILTIN_PROFILES["deepseek"],
        _fixture("deepseek", "chat.json"),
    )
    assert usage.fresh_input == 40
    assert usage.cache_read == 60
    assert usage.output == 10


def test_openrouter_non_stream_body_reports_cost() -> None:
    usage = parse_usage_body(
        Provider.OPENAI,
        Endpoint.CHAT,
        BUILTIN_PROFILES["openrouter"],
        _fixture("openrouter", "chat.json"),
    )
    assert usage.fresh_input == 44
    assert usage.provider_cost_usd == 0.00042


def test_done_sentinel_is_optional() -> None:
    data = _fixture("openai", "chat_stream_usage.sse").replace(b"data: [DONE]\n\n", b"")
    parser = new_usage_parser(Provider.OPENAI, Endpoint.CHAT, BUILTIN_PROFILES["openai"])
    _feed(parser, data)
    assert parser.result().source == "provider"


def test_mid_stream_error_event_does_not_raise() -> None:
    parser = new_usage_parser(Provider.OPENAI, Endpoint.CHAT, BUILTIN_PROFILES["openai"])
    parser.feed(
        b'data: {"id":"c1","object":"chat.completion.chunk",'
        b'"error":{"code":"server_error","message":"Provider disconnected"},'
        b'"choices":[{"index":0,"delta":{},"finish_reason":"error"}]}\n\n'
    )
    assert parser.result().source == "none"


def test_openrouter_usage_chunk_with_content_free_choice() -> None:
    parser = new_usage_parser(Provider.OPENAI, Endpoint.CHAT, BUILTIN_PROFILES["openrouter"])
    _feed(parser, _fixture("openrouter", "chat_stream_usage.sse"))
    usage = parser.result()
    assert usage.output == 2
    assert usage.provider_cost_usd is not None
