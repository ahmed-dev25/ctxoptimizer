"""Conservative break-even estimate for ``stale_result_elision`` (P6-4)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StaleElisionEstimate:
    elided_tokens: int
    batch_turns: int
    savings_per_request_usd: float
    boundary_miss_cost_usd: float
    requests_to_recover: float | None
    break_even_within_batch: bool
    method: str


def estimate_stale_elision(
    *,
    elided_tokens: int,
    batch_turns: int,
    input_per_mtok: float,
    cache_read_per_mtok: float,
    cache_write_per_mtok: float = 0.0,
) -> StaleElisionEstimate:
    """Estimate the trade-off. All money is simulated, never billed."""
    tokens = max(int(elided_tokens), 0)
    batch = max(int(batch_turns), 1)
    savings = tokens * max(input_per_mtok, 0.0) / 1_000_000
    miss = (
        tokens * max(input_per_mtok + cache_write_per_mtok - cache_read_per_mtok, 0.0) / 1_000_000
    )
    recover = (miss / savings) if savings > 0 else None
    return StaleElisionEstimate(
        elided_tokens=tokens,
        batch_turns=batch,
        savings_per_request_usd=savings,
        boundary_miss_cost_usd=miss,
        requests_to_recover=recover,
        break_even_within_batch=(recover is not None and recover <= batch),
        method=(
            "sim.: assumes elided tokens would otherwise be fresh input; one "
            "cache-miss per boundary advance at input + write - read rates."
        ),
    )


__all__ = ["StaleElisionEstimate", "estimate_stale_elision"]
