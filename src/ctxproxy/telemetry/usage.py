"""Incremental SSE and JSON usage parsers (SPEC section 14.1).

P1-2 ships the null parser so the forwarding path can be built and tested.
Provider parsers land in P1-3/P1-8.
"""

from __future__ import annotations

from typing import Protocol

from ctxproxy.models import Provider, Usage
from ctxproxy.profiles import UpstreamProfile


class UsageParser(Protocol):
    """Side-channel parser fed raw upstream bytes; never raises outward."""

    def feed(self, chunk: bytes) -> None: ...

    def disable(self) -> None: ...

    def result(self) -> Usage: ...


class NullUsageParser:
    """Records that usage is unavailable, without inspecting the stream."""

    def __init__(self) -> None:
        self._disabled = False

    def feed(self, chunk: bytes) -> None:
        return

    def disable(self) -> None:
        self._disabled = True

    @property
    def disabled(self) -> bool:
        return self._disabled

    def result(self) -> Usage:
        return Usage(source="none")


def new_usage_parser(provider: Provider, profile: UpstreamProfile) -> UsageParser:
    """Return the parser for one request. P1-3 adds provider implementations."""
    return NullUsageParser()


__all__ = ["NullUsageParser", "UsageParser", "new_usage_parser"]
