"""Transform pipeline: ordering, journal, budget and no-regress (SPEC 12.7)."""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ctxproxy.analysis.segments import Segment
from ctxproxy.config import Config
from ctxproxy.models import Mode, RequestContext, ToolResultRef, TransformReport
from ctxproxy.providers.base import ProviderAdapter
from ctxproxy.transforms.base import Transform

_CACHE_MARKER_TRANSFORMS = frozenset({"anthropic_cache", "openai_hints"})


@dataclass(frozen=True, slots=True)
class PipelineResult:
    reports: list[TransformReport]
    original_segments: list[Segment]
    final_segments: list[Segment]
    orig_est_tokens: int
    final_est_tokens: int
    changed: bool
    shadow: bool
    changed_blocks: list[tuple[str, str]]


def run_pipeline(
    ctx: RequestContext,
    payload: dict[str, Any],
    adapter: ProviderAdapter,
    transforms: Sequence[Transform],
    config: Config,
) -> PipelineResult:
    """Run transforms in order, reverting failures and non-saving changes."""
    original_segments = adapter.segments(payload)
    orig_tokens = _token_total(original_segments)
    reports: list[TransformReport] = []
    changed_blocks: list[tuple[str, str]] = []
    started = time.perf_counter()
    budget = config.pipeline.time_budget_ms

    for transform in transforms:
        elapsed_ms = (time.perf_counter() - started) * 1000
        if elapsed_ms > budget:
            reports.append(
                TransformReport(transform_id=transform.id, ran=False, discarded_reason="budget")
            )
            continue
        if not transform.applies(ctx, payload, adapter):
            continue
        before_tokens = _token_total(adapter.segments(payload))
        snapshot = _snapshot(adapter, payload)
        try:
            report = transform.apply(ctx, payload, adapter, config)
        except Exception as exc:
            _restore(snapshot)
            reports.append(
                TransformReport(
                    transform_id=transform.id,
                    ran=True,
                    discarded_reason="error",
                    error=str(exc),
                )
            )
            continue
        after_tokens = _token_total(adapter.segments(payload))
        if (
            report.changed
            and transform.id not in _CACHE_MARKER_TRANSFORMS
            and before_tokens - after_tokens < config.pipeline.min_saving_tokens
        ):
            _restore(snapshot)
            report.changed = False
            report.discarded_reason = "no_regress"
            report.est_tokens_after = report.est_tokens_before
            report.bytes_after = report.bytes_before
        if report.changed and report.discarded_reason is None:
            for ref, previous in snapshot:
                current = ref.get_text()
                if current is not None and current != previous:
                    changed_blocks.append((previous, current))
        reports.append(report)

    final_segments = adapter.segments(payload)
    return PipelineResult(
        reports=reports,
        original_segments=original_segments,
        final_segments=final_segments,
        orig_est_tokens=orig_tokens,
        final_est_tokens=_token_total(final_segments),
        changed=any(report.changed and report.discarded_reason is None for report in reports),
        shadow=ctx.mode is Mode.SHADOW,
        changed_blocks=changed_blocks,
    )


def _snapshot(adapter: ProviderAdapter, payload: dict[str, Any]) -> list[tuple[ToolResultRef, str]]:
    snapshot: list[tuple[ToolResultRef, str]] = []
    for ref in adapter.iter_tool_results(payload):
        text = ref.get_text()
        if text is not None:
            snapshot.append((ref, text))
    return snapshot


def _restore(snapshot: list[tuple[ToolResultRef, str]]) -> None:
    for ref, text in snapshot:
        ref.set_text(text)


def _token_total(segments: list[Segment]) -> int:
    return sum(segment.est_tokens for segment in segments)


__all__ = ["PipelineResult", "run_pipeline"]
