"""Property test: parsers never raise on arbitrary bytes or chunking."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from ctxoptimizer.models import Endpoint, Provider
from ctxoptimizer.profiles import BUILTIN_PROFILES
from ctxoptimizer.telemetry.usage import new_usage_parser


@settings(max_examples=60, deadline=None)
@given(st.binary(max_size=2048), st.integers(min_value=1, max_value=64))
def test_anthropic_parser_is_total(data: bytes, chunk_size: int) -> None:
    parser = new_usage_parser(Provider.ANTHROPIC, Endpoint.MESSAGES, BUILTIN_PROFILES["anthropic"])
    for start in range(0, len(data), chunk_size):
        parser.feed(data[start : start + chunk_size])
    assert parser.result().source in {"provider", "estimated", "none"}


@settings(max_examples=60, deadline=None)
@given(st.binary(max_size=2048), st.integers(min_value=1, max_value=64))
def test_chat_parser_is_total(data: bytes, chunk_size: int) -> None:
    parser = new_usage_parser(Provider.OPENAI, Endpoint.CHAT, BUILTIN_PROFILES["openai"])
    for start in range(0, len(data), chunk_size):
        parser.feed(data[start : start + chunk_size])
    assert parser.result().source in {"provider", "estimated", "none"}


@settings(max_examples=60, deadline=None)
@given(st.binary(max_size=2048), st.integers(min_value=1, max_value=64))
def test_responses_parser_is_total(data: bytes, chunk_size: int) -> None:
    parser = new_usage_parser(Provider.OPENAI, Endpoint.RESPONSES, BUILTIN_PROFILES["openai"])
    for start in range(0, len(data), chunk_size):
        parser.feed(data[start : start + chunk_size])
    assert parser.result().source in {"provider", "estimated", "none"}
