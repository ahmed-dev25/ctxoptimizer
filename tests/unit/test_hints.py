"""Cache-hint transforms: Anthropic breakpoints and OpenAI prompt keys (P4)."""

from __future__ import annotations

from typing import Any

from ctxproxy.config import Config
from ctxproxy.models import Endpoint, Mode, Provider, RequestContext
from ctxproxy.providers import adapter_for
from ctxproxy.transforms.anthropic_cache import AnthropicCache
from ctxproxy.transforms.openai_hints import OpenAIHints


def _ctx(
    config: Config,
    *,
    provider: Provider = Provider.ANTHROPIC,
    endpoint: Endpoint = Endpoint.MESSAGES,
    upstream: str = "anthropic",
) -> RequestContext:
    return RequestContext(
        request_id="req",
        provider=provider,
        endpoint=endpoint,
        upstream_name=upstream,
        model="test",
        stream=False,
        mode=Mode.ACTIVE,
        session_id="session-1",
        project=None,
        client_name="test",
        config=config,
        config_hash=config.config_hash,
        started_monotonic=0.0,
    )


def _anthropic_payload() -> dict[str, Any]:
    return {
        "model": "claude-sonnet-4-5",
        "system": "You are an agent.",
        "messages": [
            {"role": "user", "content": "one"},
            {"role": "assistant", "content": [{"type": "text", "text": "two"}]},
            {"role": "user", "content": [{"type": "text", "text": "three"}]},
            {"role": "assistant", "content": [{"type": "text", "text": "four"}]},
            {"role": "user", "content": [{"type": "text", "text": "five"}]},
        ],
    }


def test_anthropic_cache_injects_breakpoints() -> None:
    config = Config()
    payload = _anthropic_payload()
    adapter = adapter_for(Provider.ANTHROPIC, Endpoint.MESSAGES)
    report = AnthropicCache().apply(_ctx(config), payload, adapter, config)
    assert report.changed is True
    assert payload["system"][-1]["cache_control"]["type"] == "ephemeral"
    assert payload["messages"][-3]["content"][-1]["cache_control"]["type"] == "ephemeral"
    assert payload["messages"][-1]["content"][-1]["cache_control"]["type"] == "ephemeral"
    again = AnthropicCache().apply(_ctx(config), payload, adapter, config)
    assert again.changed is False


def test_anthropic_cache_respects_existing_markers() -> None:
    config = Config()
    payload = _anthropic_payload()
    payload["system"] = [
        {"type": "text", "text": "You are an agent.", "cache_control": {"type": "ephemeral"}}
    ]
    payload["messages"][-1]["content"][-1]["cache_control"] = {"type": "ephemeral"}
    adapter = adapter_for(Provider.ANTHROPIC, Endpoint.MESSAGES)
    report = AnthropicCache().apply(_ctx(config), payload, adapter, config)
    assert report.notes["existing"] == 2
    assert payload["system"][-1]["cache_control"]["type"] == "ephemeral"
    assert report.items_touched <= 2


def test_openai_hints_injects_key_for_api_openai() -> None:
    config = Config.model_validate(
        {
            "transforms": {"openai_hints": {"enabled": True}},
            "upstreams": {"openai": "https://api.openai.com"},
        }
    )
    payload: dict[str, Any] = {"model": "gpt-6.1-sol", "messages": []}
    adapter = adapter_for(Provider.OPENAI, Endpoint.CHAT)
    ctx = _ctx(config, provider=Provider.OPENAI, endpoint=Endpoint.CHAT, upstream="openai")
    assert OpenAIHints().applies(ctx, payload, adapter) is True
    report = OpenAIHints().apply(ctx, payload, adapter, config)
    assert report.changed is True
    assert str(payload["prompt_cache_key"]).startswith("ctxp-")
    assert OpenAIHints().applies(ctx, payload, adapter) is False


def test_openai_hints_dont_touch_third_party_hosts() -> None:
    config = Config.model_validate(
        {
            "transforms": {"openai_hints": {"enabled": True}},
            "upstreams": {"openai": "https://example.com"},
        }
    )
    payload: dict[str, Any] = {"model": "m"}
    adapter = adapter_for(Provider.OPENAI, Endpoint.CHAT)
    ctx = _ctx(config, provider=Provider.OPENAI, endpoint=Endpoint.CHAT, upstream="openai")
    assert OpenAIHints().applies(ctx, payload, adapter) is False


def test_openai_hints_injects_stream_usage_when_opted_in() -> None:
    config = Config.model_validate(
        {
            "transforms": {
                "openai_hints": {
                    "enabled": True,
                    "send_prompt_cache_key": False,
                    "inject_stream_usage": True,
                }
            },
            "upstreams": {"openai": "https://api.openai.com"},
        }
    )
    payload: dict[str, Any] = {"model": "gpt-6.1-sol", "messages": [], "stream": True}
    adapter = adapter_for(Provider.OPENAI, Endpoint.CHAT)
    ctx = _ctx(config, provider=Provider.OPENAI, endpoint=Endpoint.CHAT, upstream="openai")
    assert OpenAIHints().applies(ctx, payload, adapter) is True
    report = OpenAIHints().apply(ctx, payload, adapter, config)
    assert report.changed is True
    assert payload["stream_options"]["include_usage"] is True
    assert "prompt_cache_key" not in payload
    assert OpenAIHints().applies(ctx, payload, adapter) is False
