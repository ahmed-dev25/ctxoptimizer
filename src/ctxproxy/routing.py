"""Request classification and upstream selection (SPEC section 8).

Pure functions: no Starlette, no I/O. Given method/path/query/headers and the
config, produce a :class:`Route` describing where the request goes and how it
should be treated. The server layer decides what to do with it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ctxproxy.config import Config, UpstreamEntry
from ctxproxy.models import Endpoint, Mode, Provider

ADMIN_PREFIX = "/_ctxproxy"
PROJECT_PREFIX = "/p/"
UPSTREAM_PREFIX = "/u/"

_MODE_HEADERS = ("x-ctxproxy-mode", "x-ctxproxy-bypass")
_LOOPBACK_MODES = frozenset({"passthrough", "shadow", "active"})


class UnknownUpstream(LookupError):
    """Raised when ``/u/<name>`` names an upstream that is not configured."""


@dataclass(frozen=True, slots=True)
class Route:
    """Where one request is forwarded and how it is classified."""

    provider: Provider
    endpoint: Endpoint
    upstream_name: str
    upstream_base: str
    path: str
    query: str
    project: str | None
    mode: Mode
    session_id: str
    client_name: str | None

    def upstream_url(self) -> str:
        """Build the absolute upstream URL, preserving path and raw query."""
        base = self.upstream_base.rstrip("/")
        path = self.path if self.path.startswith("/") else f"/{self.path}"
        if self.query:
            return f"{base}{path}?{self.query}"
        return f"{base}{path}"


def is_absolute_target(raw_target: str) -> bool:
    """Return True for absolute-form request targets (SEC-11)."""
    lowered = raw_target.lower()
    return lowered.startswith("http://") or lowered.startswith("https://")


def classify(
    method: str,
    path: str,
    query: str,
    headers: Mapping[str, str],
    config: Config,
) -> Route:
    """Classify one request. Raises UnknownUpstream for unknown ``/u/`` names."""
    lowered = {name.lower(): value for name, value in headers.items()}
    project = lowered.get("x-ctxproxy-project") or None
    remaining = path

    if remaining.startswith(PROJECT_PREFIX):
        project_part, _, tail = remaining[len(PROJECT_PREFIX) :].partition("/")
        if project_part:
            project = project or project_part
            remaining = f"/{tail}"

    if remaining.startswith(UPSTREAM_PREFIX):
        name, _, tail = remaining[len(UPSTREAM_PREFIX) :].partition("/")
        if not name:
            raise UnknownUpstream("missing upstream name after /u/")
        base, kind = _resolve_upstream(name, config)
        remaining = _normalise_path(tail)
        provider, endpoint = _detect_for_kind(kind, method, remaining, lowered)
        return _route(
            provider=provider,
            endpoint=endpoint,
            upstream_name=name,
            upstream_base=base,
            path=remaining,
            query=query,
            project=project,
            headers=lowered,
            config=config,
        )

    provider, endpoint, upstream_name = detect(method, remaining, lowered)
    base, _ = _resolve_upstream(upstream_name, config)
    return _route(
        provider=provider,
        endpoint=endpoint,
        upstream_name=upstream_name,
        upstream_base=base,
        path=remaining,
        query=query,
        project=project,
        headers=lowered,
        config=config,
    )


def detect(method: str, path: str, headers: Mapping[str, str]) -> tuple[Provider, Endpoint, str]:
    """Auto-detect provider/endpoint from the path (SPEC section 8.2)."""
    if _is_anthropic_messages(path, method):
        return Provider.ANTHROPIC, Endpoint.MESSAGES, Provider.ANTHROPIC.value
    if _is_anthropic_passthrough(path):
        return Provider.ANTHROPIC, Endpoint.PASSTHROUGH, Provider.ANTHROPIC.value
    if _is_openai_chat(path, method):
        return Provider.OPENAI, Endpoint.CHAT, Provider.OPENAI.value
    if _is_openai_responses(path, method):
        return Provider.OPENAI, Endpoint.RESPONSES, Provider.OPENAI.value
    if _is_openai_passthrough(path, method):
        return Provider.OPENAI, Endpoint.PASSTHROUGH, Provider.OPENAI.value
    if _is_gemini(path, method):
        return Provider.GEMINI, Endpoint.GENERATE, Provider.GEMINI.value
    if _is_ollama(path, method):
        endpoint = Endpoint.CHAT if path.endswith("/chat") else Endpoint.GENERATE
        return Provider.OLLAMA, endpoint, Provider.OLLAMA.value
    if path.startswith("/v1/models"):
        anthropic = "anthropic-version" in headers or "x-api-key" in headers
        provider = Provider.ANTHROPIC if anthropic else Provider.OPENAI
        return provider, Endpoint.PASSTHROUGH, provider.value
    return Provider.OPENAI, Endpoint.PASSTHROUGH, Provider.OPENAI.value


def _detect_for_kind(
    kind: str | None, method: str, path: str, headers: Mapping[str, str]
) -> tuple[Provider, Endpoint]:
    if kind == "anthropic":
        provider = Provider.ANTHROPIC
        if _is_anthropic_messages(path, method):
            return provider, Endpoint.MESSAGES
        return provider, Endpoint.PASSTHROUGH
    if kind == "openai":
        provider = Provider.OPENAI
        if _is_openai_chat(path, method):
            return provider, Endpoint.CHAT
        if _is_openai_responses(path, method):
            return provider, Endpoint.RESPONSES
        return provider, Endpoint.PASSTHROUGH
    if kind == "gemini":
        return Provider.GEMINI, Endpoint.GENERATE
    if kind == "ollama":
        endpoint = Endpoint.CHAT if path.endswith("/chat") else Endpoint.GENERATE
        return Provider.OLLAMA, endpoint
    provider, endpoint, _ = detect(method, path, headers)
    return provider, endpoint


def _route(
    *,
    provider: Provider,
    endpoint: Endpoint,
    upstream_name: str,
    upstream_base: str,
    path: str,
    query: str,
    project: str | None,
    headers: Mapping[str, str],
    config: Config,
) -> Route:
    return Route(
        provider=provider,
        endpoint=endpoint,
        upstream_name=upstream_name,
        upstream_base=upstream_base,
        path=path,
        query=query,
        project=project,
        mode=_mode(headers, config),
        session_id=headers.get("x-ctxproxy-session", ""),
        client_name=_client_name(headers.get("user-agent", "")),
    )


def _mode(headers: Mapping[str, str], config: Config) -> Mode:
    bypass = headers.get("x-ctxproxy-bypass", "").lower()
    if bypass in {"1", "true", "yes"}:
        return Mode.PASSTHROUGH
    requested = headers.get("x-ctxproxy-mode", "").lower()
    if requested in _LOOPBACK_MODES:
        return Mode(requested)
    return Mode(config.mode.default)


def _client_name(user_agent: str) -> str | None:
    lowered = user_agent.lower()
    if "claude" in lowered:
        return "claude-code"
    if "aider" in lowered:
        return "aider"
    if "opencode" in lowered:
        return "opencode"
    if "codex" in lowered:
        return "codex"
    if "openai" in lowered:
        return "openai-sdk"
    if "anthropic" in lowered:
        return "anthropic-sdk"
    if "httpx" in lowered:
        return "python-httpx"
    return None


def _resolve_upstream(name: str, config: Config) -> tuple[str, str | None]:
    entry: str | UpstreamEntry | None = config.upstreams.get(name)
    if entry is None:
        raise UnknownUpstream(f"unknown upstream: {name}")
    if isinstance(entry, str):
        return entry, None
    return entry.url, entry.kind


def _normalise_path(tail: str) -> str:
    if not tail:
        return "/"
    return tail if tail.startswith("/") else f"/{tail}"


def _is_anthropic_messages(path: str, method: str) -> bool:
    return method == "POST" and path.rstrip("/").endswith("/messages")


def _is_anthropic_passthrough(path: str) -> bool:
    return (
        "/messages/count_tokens" in path
        or "/messages/batches" in path
        or "/files" in path
        or "/skills" in path
    )


def _is_openai_chat(path: str, method: str) -> bool:
    return method == "POST" and path.rstrip("/").endswith("/chat/completions")


def _is_openai_responses(path: str, method: str) -> bool:
    return method == "POST" and path.rstrip("/").endswith("/responses")


def _is_openai_passthrough(path: str, method: str) -> bool:
    if method != "POST":
        return False
    return any(
        path.rstrip("/").endswith(suffix) for suffix in ("/embeddings", "/moderations")
    ) or any(segment in path for segment in ("/audio/", "/images/"))


def _is_gemini(path: str, method: str) -> bool:
    return method == "POST" and (":generateContent" in path or ":streamGenerateContent" in path)


def _is_ollama(path: str, method: str) -> bool:
    if method != "POST":
        return False
    return path.rstrip("/").endswith("/api/chat") or path.rstrip("/").endswith("/api/generate")


__all__ = ["Route", "UnknownUpstream", "classify", "detect", "is_absolute_target"]
