"""Provider adapter factory (SPEC section 11)."""

from __future__ import annotations

from ctxproxy.models import Endpoint, Provider
from ctxproxy.providers.anthropic import AnthropicAdapter
from ctxproxy.providers.base import PassthroughAdapter, ProviderAdapter
from ctxproxy.providers.openai_chat import OpenAIChatAdapter
from ctxproxy.providers.openai_responses import OpenAIResponsesAdapter


def adapter_for(provider: Provider, endpoint: Endpoint) -> ProviderAdapter:
    if provider is Provider.ANTHROPIC:
        return AnthropicAdapter()
    if provider is Provider.OPENAI:
        if endpoint is Endpoint.RESPONSES:
            return OpenAIResponsesAdapter()
        return OpenAIChatAdapter()
    return PassthroughAdapter(provider)


__all__ = [
    "AnthropicAdapter",
    "OpenAIChatAdapter",
    "OpenAIResponsesAdapter",
    "PassthroughAdapter",
    "ProviderAdapter",
    "adapter_for",
]
