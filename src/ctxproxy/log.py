"""Logging setup and secret sanitization (SPEC section 17, SEC-2).

Nothing in this proxy may write credentials to a log. Call
:func:`sanitize_headers` and :func:`sanitize_url` at every log site that can
see client traffic; the values stay untouched on the forwarding path.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

REDACTED = "REDACTED"

SENSITIVE_HEADERS = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "x-api-key",
        "x-goog-api-key",
        "api-key",
        "cookie",
        "set-cookie",
        "x-ctxproxy-admin-token",
    }
)

SENSITIVE_QUERY_KEYS = frozenset({"key", "api_key", "apikey", "access_token", "token", "auth"})


def sanitize_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Return a copy of *headers* with credential values redacted."""
    return {
        name: REDACTED if name.lower() in SENSITIVE_HEADERS else value
        for name, value in headers.items()
    }


def sanitize_url(url: str) -> str:
    """Return a log-safe form of *url* with credentials and keys redacted."""
    parts = urlsplit(url)
    netloc = parts.netloc
    if "@" in netloc:
        netloc = f"{REDACTED}@{netloc.rsplit('@', 1)[1]}"
    query = [
        (name, REDACTED if name.lower() in SENSITIVE_QUERY_KEYS else value)
        for name, value in parse_qsl(parts.query, keep_blank_values=True)
    ]
    return urlunsplit((parts.scheme, netloc, parts.path, urlencode(query), parts.fragment))


def configure_logging(level: str = "info") -> None:
    """Configure the root logger once, at the requested level."""
    numeric = logging.getLevelNamesMapping().get(level.upper())
    if numeric is None:
        raise ValueError(f"unknown log level: {level!r}")
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        root.addHandler(handler)
    root.setLevel(numeric)


__all__ = [
    "REDACTED",
    "SENSITIVE_HEADERS",
    "SENSITIVE_QUERY_KEYS",
    "configure_logging",
    "sanitize_headers",
    "sanitize_url",
]
