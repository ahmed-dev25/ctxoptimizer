"""Per-upstream profiles (ADR 0006).

A profile answers the questions the proxy needs in order to treat a host
correctly: which usage shape it speaks, how its cache behaves, whether cost comes
from our pricing table or the provider, and whether cache hints may be injected.

Protocol detection stays in :mod:`ctxoptimizer.routing`; this module only resolves
names to URLs and profiles.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from ctxoptimizer.config import (
    CachePolicy,
    Config,
    CostSource,
    UpstreamEntry,
    UpstreamKind,
    UsageStyle,
)


class UnknownUpstream(LookupError):
    """Raised when a named upstream is not configured."""


@dataclass(frozen=True, slots=True)
class UpstreamProfile:
    kind: UpstreamKind | None
    usage: UsageStyle
    cache_policy: CachePolicy
    cost_source: CostSource
    cache_hints: bool
    inject_stream_usage: bool
    pricing_provider: str


@dataclass(frozen=True, slots=True)
class ResolvedUpstream:
    name: str
    url: str
    profile: UpstreamProfile


BUILTIN_PROFILES: dict[str, UpstreamProfile] = {
    "anthropic": UpstreamProfile(
        "anthropic",
        "anthropic",
        "explicit-anthropic",
        "pricing",
        True,
        False,
        "anthropic",
    ),
    "openai": UpstreamProfile(
        "openai", "openai", "implicit-openai", "pricing", True, False, "openai"
    ),
    "gemini": UpstreamProfile(
        "gemini", "gemini", "gemini-implicit", "pricing", False, False, "gemini"
    ),
    "ollama": UpstreamProfile("ollama", "ollama", "none", "none", False, False, "ollama"),
    "deepseek": UpstreamProfile(
        "openai", "deepseek", "automatic-deepseek", "pricing", False, False, "deepseek"
    ),
    "deepseek-anthropic": UpstreamProfile(
        "anthropic",
        "anthropic",
        "automatic-deepseek",
        "pricing",
        False,
        False,
        "deepseek",
    ),
    "openrouter": UpstreamProfile(
        "openai", "openrouter", "implicit-openai", "provider", False, False, "openrouter"
    ),
    "gemini-openai": UpstreamProfile(
        "openai", "gemini-openai", "gemini-implicit", "pricing", False, False, "gemini"
    ),
    "ollama-openai": UpstreamProfile(
        "openai", "ollama-openai", "none", "none", False, False, "ollama"
    ),
}


def resolve_upstream(name: str, config: Config) -> ResolvedUpstream:
    """Resolve a configured upstream name to its URL and effective profile."""
    entry = config.upstreams.get(name)
    if entry is None:
        raise UnknownUpstream(f"unknown upstream: {name}")
    if isinstance(entry, str):
        profile = BUILTIN_PROFILES.get(name) or _default_profile(None, entry, name)
        return ResolvedUpstream(name=name, url=entry, profile=profile)
    profile = _profile_for_entry(name, entry)
    return ResolvedUpstream(name=name, url=entry.url, profile=profile)


def _profile_for_entry(name: str, entry: UpstreamEntry) -> UpstreamProfile:
    builtin = BUILTIN_PROFILES.get(name)
    base = builtin or _default_profile(entry.kind, entry.url, name)
    return UpstreamProfile(
        kind=entry.kind,
        usage=entry.usage or base.usage,
        cache_policy=entry.cache_policy or base.cache_policy,
        cost_source=entry.cost_source or base.cost_source,
        cache_hints=base.cache_hints if entry.cache_hints is None else entry.cache_hints,
        inject_stream_usage=(
            base.inject_stream_usage
            if entry.inject_stream_usage is None
            else entry.inject_stream_usage
        ),
        pricing_provider=entry.pricing_provider or base.pricing_provider,
    )


def _default_profile(kind: UpstreamKind | None, url: str, name: str) -> UpstreamProfile:
    host = (urlsplit(url).hostname or "").lower()
    if kind == "anthropic":
        return UpstreamProfile(
            kind,
            "anthropic",
            "explicit-anthropic",
            "pricing",
            host == "api.anthropic.com",
            False,
            name,
        )
    if kind == "gemini":
        return UpstreamProfile(kind, "gemini", "gemini-implicit", "pricing", False, False, name)
    if kind == "ollama":
        return UpstreamProfile(kind, "ollama", "none", "none", False, False, name)
    return UpstreamProfile(
        kind,
        "openai",
        "implicit-openai",
        "pricing",
        host == "api.openai.com",
        False,
        name,
    )


__all__ = [
    "BUILTIN_PROFILES",
    "ResolvedUpstream",
    "UnknownUpstream",
    "UpstreamProfile",
    "resolve_upstream",
]
