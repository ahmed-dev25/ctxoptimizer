"""Session and project identification (SPEC section 13.1)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from hashlib import blake2b, sha256
from typing import Any

from ctxproxy.models import Provider
from ctxproxy.providers.base import ProviderAdapter

_WORKDIR_PATTERNS = (
    re.compile(r"Working directory:\s*(\S+)"),
    re.compile(r"<cwd>(.*?)</cwd>"),
    re.compile(r"Primary working directory:\s*(\S+)"),
)


def key_fingerprint(headers: Mapping[str, str]) -> str:
    """Stable fingerprint of the client credential; the raw key is never kept."""
    value = headers.get("x-api-key") or headers.get("authorization") or ""
    if not value:
        return "anonymous"
    return sha256(value.encode("utf-8")).hexdigest()[:12]


def derive_session_id(
    provider: Provider,
    headers: Mapping[str, str],
    payload: dict[str, Any],
    adapter: ProviderAdapter,
) -> str:
    system = adapter.system_text(payload)[:4096]
    tool_names = "|".join(adapter.tool_names(payload))
    first_user = adapter.first_user_text(payload)[:2048]
    system_hash = blake2b((system + tool_names).encode("utf-8"), digest_size=8).hexdigest()
    user_hash = blake2b(first_user.encode("utf-8"), digest_size=8).hexdigest()
    material = "|".join((provider.value, key_fingerprint(headers), system_hash, user_hash))
    return sha256(material.encode("utf-8")).hexdigest()[:16]


def project_from_text(text: str) -> str | None:
    for pattern in _WORKDIR_PATTERNS:
        match = pattern.search(text)
        if match:
            value = match.group(1).strip().rstrip("/\\")
            if value:
                return value.replace("\\", "/").split("/")[-1]
    return None


def project_from_payload(payload: dict[str, Any], adapter: ProviderAdapter) -> str | None:
    return project_from_text(f"{adapter.system_text(payload)}\n{adapter.first_user_text(payload)}")


__all__ = [
    "derive_session_id",
    "key_fingerprint",
    "project_from_payload",
    "project_from_text",
]
