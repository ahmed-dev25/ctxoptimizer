"""Adapters, segments, session derivation and token estimation (P2-1/P2-2)."""

from __future__ import annotations

from typing import Any

from ctxoptimizer.analysis.segments import block_hash, make_segment
from ctxoptimizer.analysis.session import derive_session_id, key_fingerprint, project_from_payload
from ctxoptimizer.analysis.tokens import Calibrator, estimate_tokens
from ctxoptimizer.models import Endpoint, Provider
from ctxoptimizer.providers import adapter_for


def _anthropic_payload() -> dict[str, Any]:
    return {
        "model": "claude-sonnet-4-5",
        "stream": True,
        "system": [
            {
                "type": "text",
                "text": "You are an agent.\nWorking directory: /home/user/proj",
                "cache_control": {"type": "ephemeral"},
            }
        ],
        "tools": [{"name": "Read", "input_schema": {"type": "object"}}],
        "messages": [
            {"role": "user", "content": "read the file"},
            {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "toolu_1", "name": "Read", "input": {}}],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_1",
                        "content": "hello world",
                        "is_error": False,
                    }
                ],
            },
        ],
    }


def test_anthropic_tool_results_and_names() -> None:
    adapter = adapter_for(Provider.ANTHROPIC, Endpoint.MESSAGES)
    refs = list(adapter.iter_tool_results(_anthropic_payload()))
    assert len(refs) == 1
    ref = refs[0]
    assert ref.tool_use_id == "toolu_1"
    assert ref.tool_name == "Read"
    assert ref.get_text() == "hello world"
    ref.set_text("short")
    assert ref.get_text() == "short"


def test_anthropic_segments_order_and_marker() -> None:
    adapter = adapter_for(Provider.ANTHROPIC, Endpoint.MESSAGES)
    segments = adapter.segments(_anthropic_payload())
    assert [segment.kind for segment in segments][:2] == ["tool_def", "system"]
    assert segments[1].has_marker is True
    assert len(segments) == 5
    assert segments[0].est_tokens > 0


def test_block_hash_ignores_cache_marker() -> None:
    plain = {"type": "text", "text": "same"}
    marked = {**plain, "cache_control": {"type": "ephemeral"}}
    assert block_hash(plain) == block_hash(marked)
    assert make_segment("system", marked).has_marker is True


def test_session_derivation_is_stable_and_project_extracted() -> None:
    adapter = adapter_for(Provider.ANTHROPIC, Endpoint.MESSAGES)
    payload = _anthropic_payload()
    first = derive_session_id(Provider.ANTHROPIC, {"x-api-key": "sk-a"}, payload, adapter)
    second = derive_session_id(Provider.ANTHROPIC, {"x-api-key": "sk-a"}, payload, adapter)
    other = derive_session_id(Provider.ANTHROPIC, {"x-api-key": "sk-b"}, payload, adapter)
    assert first == second
    assert first != other
    assert project_from_payload(payload, adapter) == "proj"
    assert key_fingerprint({}) == "anonymous"


def test_openai_chat_tool_results() -> None:
    payload = {
        "model": "gpt-6.1-sol",
        "messages": [
            {"role": "user", "content": "run it"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "shell", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "ok"},
        ],
        "tools": [{"type": "function", "function": {"name": "shell"}}],
    }
    adapter = adapter_for(Provider.OPENAI, Endpoint.CHAT)
    refs = list(adapter.iter_tool_results(payload))
    assert len(refs) == 1
    assert refs[0].tool_name == "shell"
    assert refs[0].get_text() == "ok"
    assert len(adapter.segments(payload)) == 4


def test_openai_responses_tool_output_and_previous_response() -> None:
    payload = {
        "model": "gpt-6.1-sol",
        "instructions": "be terse",
        "tools": [{"type": "function", "name": "shell"}],
        "input": [
            {"role": "user", "content": "run"},
            {"type": "function_call", "call_id": "call_1", "name": "shell", "arguments": "{}"},
            {"type": "function_call_output", "call_id": "call_1", "output": "ok"},
        ],
    }
    adapter = adapter_for(Provider.OPENAI, Endpoint.RESPONSES)
    refs = list(adapter.iter_tool_results(payload))
    assert len(refs) == 1
    assert refs[0].tool_name == "shell"
    assert refs[0].get_text() == "ok"
    assert adapter.is_transformable(payload) is True
    payload["previous_response_id"] = "resp_1"
    assert adapter.is_transformable(payload) is False
    assert len(adapter.segments(payload)) == 5


def test_token_estimation_and_calibration() -> None:
    assert estimate_tokens("hello world") >= 1
    assert estimate_tokens("") == 0
    calibrator = Calibrator(alpha=0.5)
    calibrator.update("claude", actual=120, estimated=100)
    assert calibrator.apply("claude", 100) == 110
    calibrator.update("claude", actual=0, estimated=100)
    assert calibrator.apply("claude", 100) == 110
