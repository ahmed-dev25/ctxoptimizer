"""Stale tool-result elision (P6-4)."""

from __future__ import annotations

from typing import Any

from ctxproxy.config import Config
from ctxproxy.models import Endpoint, Mode, Provider, RequestContext
from ctxproxy.providers import adapter_for
from ctxproxy.transforms.stale_result_elision import StaleResultElision


def _config(enabled: bool = True) -> Config:
    return Config.model_validate({"transforms": {"stale_result_elision": {"enabled": enabled}}})


def _ctx(config: Config) -> RequestContext:
    return RequestContext(
        request_id="req",
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


def _payload() -> dict[str, Any]:
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": "go"},
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "old",
                    "content": "x" * 6000,
                }
            ],
        },
    ]
    messages.extend({"role": "assistant", "content": f"turn {index}"} for index in range(20))
    messages.append(
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "new",
                    "content": "y" * 6000,
                }
            ],
        }
    )
    return {"model": "claude-sonnet-4-5", "messages": messages}


def test_old_result_is_elided_and_recent_result_is_kept() -> None:
    config = _config()
    adapter = adapter_for(Provider.ANTHROPIC, Endpoint.MESSAGES)
    payload = _payload()
    report = StaleResultElision().apply(_ctx(config), payload, adapter, config)
    assert report.changed is True
    assert report.items_touched == 1
    refs = list(adapter.iter_tool_results(payload))
    old = refs[0].get_text()
    new = refs[1].get_text()
    assert old is not None and old.startswith("[ctxproxy: tool result elided (5.9 KB)")
    assert new == "y" * 6000


def test_elision_is_idempotent() -> None:
    config = _config()
    adapter = adapter_for(Provider.ANTHROPIC, Endpoint.MESSAGES)
    payload = _payload()
    transform = StaleResultElision()
    transform.apply(_ctx(config), payload, adapter, config)
    second = transform.apply(_ctx(config), payload, adapter, config)
    assert second.changed is False


def test_elision_is_off_by_default() -> None:
    config = _config(enabled=False)
    adapter = adapter_for(Provider.ANTHROPIC, Endpoint.MESSAGES)
    payload = _payload()
    assert StaleResultElision().applies(_ctx(config), payload, adapter) is False
