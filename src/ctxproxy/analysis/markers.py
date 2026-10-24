"""Client cache-marker quality (SPEC section 12.9 / P4-3)."""

from __future__ import annotations

from dataclasses import dataclass

from ctxproxy.analysis.segments import Segment


@dataclass(frozen=True, slots=True)
class MarkerQuality:
    markers: int
    cacheable_tokens: int
    total_tokens: int
    coverage: float


def marker_quality(segments: list[Segment]) -> MarkerQuality:
    markers = sum(1 for segment in segments if segment.has_marker)
    total = sum(segment.est_tokens for segment in segments)
    last = -1
    for index, segment in enumerate(segments):
        if segment.has_marker:
            last = index
    cacheable = sum(segment.est_tokens for segment in segments[: last + 1]) if last >= 0 else 0
    return MarkerQuality(
        markers=markers,
        cacheable_tokens=cacheable,
        total_tokens=total,
        coverage=(cacheable / total) if total else 0.0,
    )


__all__ = ["MarkerQuality", "marker_quality"]
