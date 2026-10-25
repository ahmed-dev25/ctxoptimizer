"""Cache baseline simulator (SPEC section 13.5)."""

from __future__ import annotations

from dataclasses import dataclass

from ctxoptimizer.analysis.segments import Segment


@dataclass(frozen=True, slots=True)
class CacheSim:
    fresh_tokens: int
    read_tokens: int
    write_5m_tokens: int
    write_1h_tokens: int


def common_prefix_tokens(previous: list[Segment], current: list[Segment]) -> int:
    total = 0
    for old, new in zip(previous, current, strict=False):
        if old.hash != new.hash:
            break
        total += new.est_tokens
    return total


def simulate(
    cache_policy: str,
    previous: list[Segment] | None,
    previous_ts: float | None,
    current: list[Segment],
    current_ts: float,
    *,
    ttl_s: float = 300.0,
    min_prefix: int = 1024,
) -> CacheSim:
    total = sum(segment.est_tokens for segment in current)
    if previous is None or previous_ts is None or current_ts - previous_ts > ttl_s:
        return CacheSim(total, 0, 0, 0)
    if cache_policy == "explicit-anthropic":
        return _explicit(previous, current, total)
    if cache_policy in {"implicit-openai", "gemini-implicit", "automatic-deepseek"}:
        prefix = common_prefix_tokens(previous, current)
        read = (prefix // 128) * 128 if prefix >= min_prefix else 0
        return CacheSim(max(0, total - read), min(total, read), 0, 0)
    return CacheSim(total, 0, 0, 0)


def _explicit(previous: list[Segment], current: list[Segment], total: int) -> CacheSim:
    previous_marker = _tokens_to_last_marker(previous)
    current_marker = _tokens_to_last_marker(current)
    if previous_marker == 0 or current_marker == 0:
        return CacheSim(total, 0, 0, 0)
    read = min(common_prefix_tokens(previous, current), previous_marker)
    write = max(0, current_marker - read)
    return CacheSim(max(0, total - read - write), read, write, 0)


def _tokens_to_last_marker(segments: list[Segment]) -> int:
    last = -1
    for index, segment in enumerate(segments):
        if segment.has_marker:
            last = index
    if last < 0:
        return 0
    return sum(segment.est_tokens for segment in segments[: last + 1])


__all__ = ["CacheSim", "common_prefix_tokens", "simulate"]
