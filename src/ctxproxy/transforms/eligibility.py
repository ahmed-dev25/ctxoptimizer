"""Tool eligibility from the ``[tools]`` globs (SPEC section 12.0.4)."""

from __future__ import annotations

from fnmatch import fnmatchcase

from ctxproxy.config import Config
from ctxproxy.models import ToolResultRef


def matches(name: str, patterns: list[str]) -> bool:
    lowered = name.lower()
    return any(fnmatchcase(lowered, pattern.lower()) for pattern in patterns)


def is_never_touch(ref: ToolResultRef, config: Config) -> bool:
    return bool(ref.tool_name and matches(ref.tool_name, config.tools.never_touch))


def is_compactable(ref: ToolResultRef, config: Config) -> bool:
    return bool(ref.tool_name and matches(ref.tool_name, config.tools.compactable))


__all__ = ["is_compactable", "is_never_touch", "matches"]
