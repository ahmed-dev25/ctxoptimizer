"""Provider adapter factory (SPEC section 11)."""

from __future__ import annotations

from ctxproxy.models import Endpoint, Provider
from ctxproxy.providers.anthropic import AnthropicAdapter
from ctxproxy.providers.base import PassthroughAdapter, ProviderAdapter
from ctxproxy.providers.gemini import GeminiAdapter
from ctxproxy.providers.ollama import OllamaAdapter
from ctxproxy.providers.openai_chat import OpenAIChatAdapter
from ctxproxy.providers.openai_responses import OpenAIResponsesAdapter


def adapter_for(provider: Provider, endpoint: Endpoint) -> ProviderAdapter:
    if provider is Provider.ANTHROPIC:
        return AnthropicAdapter()
    if provider is Provider.OPENAI:
        if endpoint is Endpoint.RESPONSES:
            return OpenAIResponsesAdapter()
        return OpenAIChatAdapter()
    if provider is Provider.GEMINI:
        return GeminiAdapter()
    if provider is Provider.OLLAMA:
        return OllamaAdapter()
    return PassthroughAdapter(provider)


__all__ = [
    "AnthropicAdapter",
    "GeminiAdapter",
    "OllamaAdapter",
    "OpenAIChatAdapter",
    "OpenAIResponsesAdapter",
    "PassthroughAdapter",
    "ProviderAdapter",
    "adapter_for",
]
