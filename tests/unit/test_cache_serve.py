"""Byte-true cross-request substitution (P3-8)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from ctxproxy.config import Config
from ctxproxy.models import Endpoint, Mode, Provider, RequestContext
from ctxproxy.providers import adapter_for
from ctxproxy.transforms.cache_serve import CacheServe, CacheServeState


def _config() -> Config:
    return Config.model_validate(
        {
            "transforms": {"cache_serve": {"enabled": True}},
            "telemetry": {"capture_payloads": "changed_blocks"},
        }
    )


def _ctx(config: Config) -> RequestContext:
    return RequestContext(
        request_id="req",
        provider=Provider.ANTHROPIC,
        endpoint=Endpoint.MESSAGES,
        upstream_name="anthropic",
        model="claude-sonnet-4-5",
        stream=False,
        mode=Mode.ACTIVE,
        session_id="session-1",
        project=None,
        client_name="test",
        config=config,
        config_hash=config.config_hash,
        started_monotonic=0.0,
    )


def _payload(assistant_turns: int, content: str) -> dict[str, Any]:
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": "go"},
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "t1", "content": content}],
        },
    ]
    messages.extend(
        {"role": "assistant", "content": f"turn {index}"} for index in range(assistant_turns)
    )
    return {"model": "claude-sonnet-4-5", "messages": messages}


def test_cache_serve_stubs_only_at_batch_boundary() -> None:
    config = _config()
    state = CacheServeState()
    transform = CacheServe(state)
    adapter = adapter_for(Provider.ANTHROPIC, Endpoint.MESSAGES)
    content = "unchanged file content " * 200

    first = _payload(0, content)
    report = transform.apply(_ctx(config), first, adapter, config)
    assert report.changed is False
    assert adapter.iter_tool_results(first).__next__().get_text() == content

    second = _payload(20, content)
    report = transform.apply(_ctx(config), second, adapter, config)
    text = adapter.iter_tool_results(second).__next__().get_text()
    assert report.changed is True
    assert text is not None and text.startswith("[ctxproxy: content identical to turn 0")
    assert "ctxproxy_expand(" in text

    third = transform.apply(_ctx(config), second, adapter, config)
    assert third.changed is False


def test_cache_serve_requires_capture() -> None:
    with pytest.raises(ValidationError):
        Config.model_validate(
            {
                "transforms": {"cache_serve": {"enabled": True}},
                "telemetry": {"capture_payloads": "off"},
            }
        )
