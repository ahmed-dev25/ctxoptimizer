"""Provider adapter factory (SPEC section 11)."""

from __future__ import annotations

from ctxoptimizer.models import Endpoint, Provider
from ctxoptimizer.providers.anthropic import AnthropicAdapter
from ctxoptimizer.providers.base import PassthroughAdapter, ProviderAdapter
from ctxoptimizer.providers.gemini import GeminiAdapter
from ctxoptimizer.providers.ollama import OllamaAdapter
from ctxoptimizer.providers.openai_chat import OpenAIChatAdapter
from ctxoptimizer.providers.openai_responses import OpenAIResponsesAdapter


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
