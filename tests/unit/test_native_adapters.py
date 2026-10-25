"""Native Gemini and Ollama adapters (P6-1/P6-2)."""

from __future__ import annotations

from typing import Any

from ctxoptimizer.models import Endpoint, Provider
from ctxoptimizer.providers import adapter_for


def _gemini_payload() -> dict[str, Any]:
    return {
        "contents": [
            {"role": "user", "parts": [{"text": "read the file"}]},
            {
                "role": "model",
                "parts": [{"functionCall": {"name": "read", "args": {"path": "a.txt"}}}],
            },
            {
                "role": "user",
                "parts": [
                    {
                        "functionResponse": {
                            "name": "read",
                            "response": {"content": "hello world"},
                        }
                    }
                ],
            },
        ],
        "systemInstruction": {"parts": [{"text": "be terse"}]},
        "tools": [
            {
                "functionDeclarations": [
                    {"name": "read", "description": "read a file", "parameters": {}}
                ]
            }
        ],
    }


def _ollama_payload() -> dict[str, Any]:
    return {
        "model": "llama3.2",
        "messages": [
            {"role": "system", "content": "be terse"},
            {"role": "user", "content": "read the file"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"function": {"name": "read", "arguments": {"path": "a.txt"}}}],
            },
            {"role": "tool", "tool_name": "read", "content": "hello world"},
        ],
        "tools": [{"type": "function", "function": {"name": "read"}}],
    }


def test_gemini_tool_result_and_segments() -> None:
    adapter = adapter_for(Provider.GEMINI, Endpoint.GENERATE)
    assert adapter.is_transformable(_gemini_payload()) is True
    refs = list(adapter.iter_tool_results(_gemini_payload()))
    assert len(refs) == 1
    ref = refs[0]
    assert ref.tool_name == "read"
    assert ref.get_text() == "hello world"
    ref.set_text("short")
    assert ref.get_text() == "short"
    assert adapter.tool_names(_gemini_payload()) == ["read"]
    assert adapter.used_tool_names(_gemini_payload()) == ["read"]
    segments = adapter.segments(_gemini_payload())
    assert [segment.kind for segment in segments][:2] == ["tool_def", "system"]
    assert len(segments) == 5


def test_gemini_function_response_mapping_forms() -> None:
    adapter = adapter_for(Provider.GEMINI, Endpoint.GENERATE)
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"functionResponse": {"name": "a", "response": "plain"}},
                    {"functionResponse": {"name": "b", "response": {"result": "nested"}}},
                ],
            }
        ]
    }
    refs = list(adapter.iter_tool_results(payload))
    assert [ref.get_text() for ref in refs] == ["plain", "nested"]


def test_ollama_tool_result_and_segments() -> None:
    adapter = adapter_for(Provider.OLLAMA, Endpoint.CHAT)
    assert adapter.is_transformable(_ollama_payload()) is True
    refs = list(adapter.iter_tool_results(_ollama_payload()))
    assert len(refs) == 1
    assert refs[0].tool_name == "read"
    assert refs[0].get_text() == "hello world"
    assert adapter.tool_names(_ollama_payload()) == ["read"]
    assert adapter.used_tool_names(_ollama_payload()) == ["read"]
    assert len(adapter.segments(_ollama_payload())) == 5


def test_ollama_generate_payload_is_measured_but_has_no_tool_results() -> None:
    adapter = adapter_for(Provider.OLLAMA, Endpoint.GENERATE)
    payload = {"model": "llama3.2", "prompt": "hello", "stream": False}
    assert adapter.is_transformable(payload) is True
    assert adapter.is_stream(payload) is False
    assert list(adapter.iter_tool_results(payload)) == []
    assert adapter.segments(payload)[0].kind == "message"
    assert adapter.first_user_text(payload) == "hello"
