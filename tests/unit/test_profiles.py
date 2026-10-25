"""Per-upstream profile resolution (ADR 0006)."""

from __future__ import annotations

import pytest

from ctxoptimizer.config import Config
from ctxoptimizer.profiles import BUILTIN_PROFILES, UnknownUpstream, resolve_upstream


def test_builtin_profiles_cover_the_default_upstreams() -> None:
    config = Config()
    assert resolve_upstream("anthropic", config).profile.usage == "anthropic"
    assert resolve_upstream("anthropic", config).profile.cache_hints is True
    assert resolve_upstream("openai", config).profile.cache_policy == "implicit-openai"
    assert resolve_upstream("ollama", config).profile.cost_source == "none"
    assert set(BUILTIN_PROFILES) >= {
        "anthropic",
        "openai",
        "gemini",
        "ollama",
        "deepseek",
        "deepseek-anthropic",
        "openrouter",
        "gemini-openai",
        "ollama-openai",
    }


def test_deepseek_string_uses_named_profile() -> None:
    config = Config.model_validate({"upstreams": {"deepseek": "https://api.deepseek.com"}})
    profile = resolve_upstream("deepseek", config).profile
    assert profile.kind == "openai"
    assert profile.usage == "deepseek"
    assert profile.cache_policy == "automatic-deepseek"
    assert profile.cache_hints is False


def test_deepseek_anthropic_disables_cache_hints() -> None:
    config = Config.model_validate(
        {
            "upstreams": {
                "deepseek-anthropic": {
                    "url": "https://api.deepseek.com/anthropic",
                    "kind": "anthropic",
                }
            }
        }
    )
    profile = resolve_upstream("deepseek-anthropic", config).profile
    assert profile.kind == "anthropic"
    assert profile.cache_policy == "automatic-deepseek"
    assert profile.cache_hints is False


def test_openrouter_reports_provider_cost() -> None:
    config = Config.model_validate({"upstreams": {"openrouter": "https://openrouter.ai/api"}})
    profile = resolve_upstream("openrouter", config).profile
    assert profile.usage == "openrouter"
    assert profile.cost_source == "provider"


def test_custom_openai_host_gets_no_hints() -> None:
    config = Config.model_validate(
        {"upstreams": {"myproxy": {"url": "https://example.com", "kind": "openai"}}}
    )
    profile = resolve_upstream("myproxy", config).profile
    assert profile.usage == "openai"
    assert profile.cache_policy == "implicit-openai"
    assert profile.cache_hints is False


def test_api_openai_gets_hints() -> None:
    config = Config.model_validate({"upstreams": {"openai": "https://api.openai.com"}})
    assert resolve_upstream("openai", config).profile.cache_hints is True


def test_custom_table_overrides_profile_fields() -> None:
    config = Config.model_validate(
        {
            "upstreams": {
                "myhost": {
                    "url": "https://example.com",
                    "kind": "openai",
                    "usage": "deepseek",
                    "cache_policy": "automatic-deepseek",
                    "cost_source": "provider",
                    "cache_hints": False,
                    "inject_stream_usage": True,
                }
            }
        }
    )
    profile = resolve_upstream("myhost", config).profile
    assert profile.usage == "deepseek"
    assert profile.cache_policy == "automatic-deepseek"
    assert profile.cost_source == "provider"
    assert profile.inject_stream_usage is True


def test_unknown_upstream_raises() -> None:
    with pytest.raises(UnknownUpstream):
        resolve_upstream("nope", Config())
