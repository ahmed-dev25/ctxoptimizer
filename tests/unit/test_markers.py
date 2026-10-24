"""Client cache-marker quality metric (P4-3)."""

from __future__ import annotations

from ctxproxy.analysis.markers import marker_quality
from ctxproxy.analysis.segments import Segment


def _segment(tokens: int, marker: bool) -> Segment:
    return Segment(
        kind="message",
        msg_index=0,
        block_index=0,
        hash=b"0" * 8,
        est_tokens=tokens,
        has_marker=marker,
    )


def test_marker_quality_counts_coverage_to_last_marker() -> None:
    result = marker_quality([_segment(10, False), _segment(30, True), _segment(20, False)])
    assert result.markers == 1
    assert result.cacheable_tokens == 40
    assert result.total_tokens == 60
    assert result.coverage == 40 / 60


def test_marker_quality_without_markers_is_zero() -> None:
    result = marker_quality([_segment(5, False)])
    assert result.markers == 0
    assert result.cacheable_tokens == 0
    assert result.coverage == 0.0
