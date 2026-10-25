"""Property tests for core transform invariants (SPEC 20.1 P1-P7)."""

from __future__ import annotations

import copy

from hypothesis import given, settings
from hypothesis import strategies as st

from ctxoptimizer.config import Config
from ctxoptimizer.models import Endpoint, Mode, Provider, RequestContext
from ctxoptimizer.pipeline import run_pipeline
from ctxoptimizer.providers import adapter_for
from ctxoptimizer.transforms import ansi, build_transforms, dedupe_lines, progress, whitespace
from ctxoptimizer.transforms.volatile import normalize_system, normalize_user_env

_ALPHABET = "abcXYZ0123 \n\t\r\x1b[]=#-.%:/"
_TEXT = st.text(alphabet=_ALPHABET, max_size=600)


def _config() -> Config:
    return Config.model_validate(
        {
            "mode": {"default": "active"},
            "transforms": {
                "anthropic_cache": {"enabled": False},
                "openai_hints": {"enabled": False},
            },
        }
    )


def _ctx(config: Config) -> RequestContext:
    return RequestContext(
        request_id="p",
        provider=Provider.ANTHROPIC,
        endpoint=Endpoint.MESSAGES,
        upstream_name="anthropic",
        model="claude-sonnet-4-5",
        stream=False,
        mode=Mode.ACTIVE,
        session_id="s",
        project=None,
        client_name="test",
        config=config,
        config_hash=config.config_hash,
        started_monotonic=0.0,
    )


def _run(payload: dict, config: Config) -> tuple[dict, object]:
    copy_payload = copy.deepcopy(payload)
    adapter = adapter_for(Provider.ANTHROPIC, Endpoint.MESSAGES)
    result = run_pipeline(_ctx(config), copy_payload, adapter, build_transforms(config), config)
    return copy_payload, result


@settings(max_examples=25, deadline=None)
@given(_TEXT)
def test_pure_transforms_are_idempotent(text: str) -> None:
    for clean in (
        ansi.clean,
        progress.clean,
        whitespace.clean,
        lambda value: dedupe_lines.clean(value, 3),
        normalize_system,
        normalize_user_env,
    ):
        once = clean(text)
        assert clean(once) == once


@settings(max_examples=20, deadline=None)
@given(_TEXT)
def test_pipeline_is_deterministic_and_idempotent(text: str) -> None:
    payload = {
        "model": "claude-sonnet-4-5",
        "messages": [
            {"role": "user", "content": "run"},
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "t1", "content": text}],
            },
        ],
    }
    first, _ = _run(payload, _config())
    second, _ = _run(payload, _config())
    assert first == second
    third, _ = _run(first, _config())
    assert third == first


def test_pairing_unknown_fields_and_reasoning_are_preserved() -> None:
    payload = {
        "model": "claude-sonnet-4-5",
        "system": [{"type": "text", "text": "sys", "cache_control": {"type": "ephemeral"}}],
        "messages": [
            {"role": "user", "content": "go"},
            {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "private reasoning", "signature": "sig"},
                    {
                        "type": "tool_use",
                        "id": "call_1",
                        "name": "Bash",
                        "input": {"command": "pytest"},
                        "extra": {"keep": True},
                    },
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "call_1",
                        "content": "\x1b[31mred\x1b[0m\nline\nline\nline\nline",
                        "extra": {"keep": "me"},
                    }
                ],
            },
        ],
    }
    result_payload, result = _run(payload, _config())
    assistant = result_payload["messages"][1]["content"]
    assert assistant[0] == {
        "type": "thinking",
        "thinking": "private reasoning",
        "signature": "sig",
    }
    assert assistant[1]["id"] == "call_1"
    assert assistant[1]["extra"] == {"keep": True}
    assert result_payload["messages"][2]["content"][0]["tool_use_id"] == "call_1"
    assert result_payload["messages"][2]["content"][0]["extra"] == {"keep": "me"}
    assert result.final_est_tokens <= result.orig_est_tokens
