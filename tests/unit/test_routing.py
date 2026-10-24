"""Routing and upstream resolution (SPEC section 8)."""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from ctxproxy.config import Config
from ctxproxy.models import Endpoint, Mode, Provider
from ctxproxy.routing import UnknownUpstream, classify, is_absolute_target


def _config() -> Config:
    return Config.model_validate(
        {
            "upstreams": {
                "anthropic": "https://api.anthropic.com",
                "openai": "https://api.openai.com",
                "gemini": "https://generativelanguage.googleapis.com",
                "ollama": "http://127.0.0.1:11434",
                "deepseek": "https://api.deepseek.com",
                "deepseek-anthropic": {
                    "url": "https://api.deepseek.com/anthropic",
                    "kind": "anthropic",
                },
            }
        }
    )


@pytest.mark.parametrize(
    ("method", "path", "provider", "endpoint"),
    [
        ("POST", "/v1/messages", Provider.ANTHROPIC, Endpoint.MESSAGES),
        ("POST", "/v1/messages/count_tokens", Provider.ANTHROPIC, Endpoint.PASSTHROUGH),
        ("POST", "/v1/chat/completions", Provider.OPENAI, Endpoint.CHAT),
        ("POST", "/v1/responses", Provider.OPENAI, Endpoint.RESPONSES),
        ("POST", "/v1/embeddings", Provider.OPENAI, Endpoint.PASSTHROUGH),
        (
            "POST",
            "/v1beta/models/gemini-2:generateContent",
            Provider.GEMINI,
            Endpoint.GENERATE,
        ),
        ("POST", "/api/chat", Provider.OLLAMA, Endpoint.CHAT),
        ("POST", "/api/generate", Provider.OLLAMA, Endpoint.GENERATE),
        ("GET", "/v1/models", Provider.OPENAI, Endpoint.PASSTHROUGH),
        ("GET", "/some/unknown/path", Provider.OPENAI, Endpoint.PASSTHROUGH),
    ],
)
def test_detection_table(method: str, path: str, provider: Provider, endpoint: Endpoint) -> None:
    route = classify(method, path, "", {}, _config())
    assert route.provider is provider
    assert route.endpoint is endpoint
    assert route.upstream_name == provider.value


def test_models_header_disambiguates_anthropic() -> None:
    route = classify("GET", "/v1/models", "", {"x-api-key": "sk-test"}, _config())
    assert route.provider is Provider.ANTHROPIC


def test_named_upstream_openai_path() -> None:
    route = classify("POST", "/u/deepseek/chat/completions", "", {}, _config())
    assert route.provider is Provider.OPENAI
    assert route.endpoint is Endpoint.CHAT
    assert route.upstream_name == "deepseek"
    assert route.upstream_base == "https://api.deepseek.com"
    assert route.path == "/chat/completions"
    assert route.upstream_url() == "https://api.deepseek.com/chat/completions"


def test_named_upstream_anthropic_kind() -> None:
    route = classify("POST", "/u/deepseek-anthropic/v1/messages", "", {}, _config())
    assert route.provider is Provider.ANTHROPIC
    assert route.endpoint is Endpoint.MESSAGES
    assert route.upstream_url() == "https://api.deepseek.com/anthropic/v1/messages"


def test_named_upstream_preserves_query() -> None:
    route = classify("POST", "/u/deepseek/chat/completions", "beta=true&x=1", {}, _config())
    assert route.upstream_url() == ("https://api.deepseek.com/chat/completions?beta=true&x=1")


def test_named_upstream_unknown_raises() -> None:
    with pytest.raises(UnknownUpstream):
        classify("POST", "/u/missing/chat/completions", "", {}, _config())


def test_project_prefix_is_stripped() -> None:
    route = classify("POST", "/p/myrepo/v1/messages", "", {}, _config())
    assert route.project == "myrepo"
    assert route.path == "/v1/messages"


def test_project_header_wins() -> None:
    route = classify(
        "POST",
        "/p/myrepo/v1/messages",
        "",
        {"x-ctxproxy-project": "other"},
        _config(),
    )
    assert route.project == "other"


def test_mode_defaults_to_config() -> None:
    route = classify("POST", "/v1/messages", "", {}, _config())
    assert route.mode is Mode.SHADOW


def test_mode_header_and_bypass() -> None:
    active = classify("POST", "/v1/messages", "", {"x-ctxproxy-mode": "active"}, _config())
    assert active.mode is Mode.ACTIVE
    bypass = classify("POST", "/v1/messages", "", {"x-ctxproxy-bypass": "1"}, _config())
    assert bypass.mode is Mode.PASSTHROUGH


def test_invalid_mode_header_is_ignored() -> None:
    route = classify("POST", "/v1/messages", "", {"x-ctxproxy-mode": "turbo"}, _config())
    assert route.mode is Mode.SHADOW


def test_client_name_from_user_agent() -> None:
    route = classify("POST", "/v1/messages", "", {"User-Agent": "claude-cli/2.0"}, _config())
    assert route.client_name == "claude-code"
    route = classify("POST", "/v1/messages", "", {"User-Agent": "opencode/2.0"}, _config())
    assert route.client_name == "opencode"


def test_absolute_target_detection() -> None:
    assert is_absolute_target("http://evil.example/v1/messages")
    assert is_absolute_target("HTTPS://evil.example/")
    assert not is_absolute_target("/v1/messages")


def test_headers_mapping_is_case_insensitive() -> None:
    headers: Mapping[str, str] = {"X-Ctxproxy-Session": "abc"}
    route = classify("POST", "/v1/messages", "", headers, _config())
    assert route.session_id == "abc"


def test_named_upstream_without_tail_uses_root() -> None:
    route = classify("GET", "/u/deepseek", "", {}, _config())
    assert route.path == "/"
    assert route.endpoint is Endpoint.PASSTHROUGH
