"""Prefix-drift detector (SPEC section 13.4)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ctxoptimizer.analysis.segments import Segment

DriftCause = Literal[
    "tools_changed",
    "system_changed",
    "params_changed",
    "history_mutated",
    "ttl_expired",
    "config_changed",
    "model_switched",
]

_CAUSE_BY_KIND: dict[str, DriftCause] = {
    "tool_def": "tools_changed",
    "system": "system_changed",
    "message": "history_mutated",
}


@dataclass(frozen=True, slots=True)
class DriftEvent:
    cause: DriftCause
    at_segment: int | None
    est_tokens_lost: int
    detail: dict[str, object]


def detect_drift(
    previous: list[Segment] | None,
    current: list[Segment],
    *,
    previous_ts: float | None = None,
    current_ts: float | None = None,
    ttl_s: float = 300.0,
    previous_params: str | None = None,
    current_params: str | None = None,
    previous_config_hash: str | None = None,
    current_config_hash: str | None = None,
    previous_model: str | None = None,
    current_model: str | None = None,
) -> DriftEvent | None:
    """Return the first divergence that would break prefix cache reuse."""
    if previous is None:
        return None
    if previous_model and current_model and previous_model != current_model:
        return DriftEvent(
            "model_switched",
            0,
            _lost(previous, current, 0),
            {"previous": previous_model, "current": current_model},
        )
    if (
        previous_params is not None
        and current_params is not None
        and previous_params != current_params
    ):
        return DriftEvent(
            "params_changed", 0, _lost(previous, current, 0), {"params": current_params}
        )
    if previous_config_hash and current_config_hash and previous_config_hash != current_config_hash:
        return DriftEvent(
            "config_changed",
            0,
            _lost(previous, current, 0),
            {"config_hash": current_config_hash},
        )

    limit = min(len(previous), len(current))
    first = next(
        (index for index in range(limit) if previous[index].hash != current[index].hash),
        None,
    )
    if first is None and len(current) < len(previous):
        first = len(current)
    if first is not None:
        kind = current[first].kind if first < len(current) else previous[first].kind
        return DriftEvent(
            _CAUSE_BY_KIND.get(kind, "history_mutated"),
            first,
            _lost(previous, current, first),
            {"kind": kind},
        )

    if previous_ts is not None and current_ts is not None:
        delta = current_ts - previous_ts
        if delta > ttl_s:
            return DriftEvent(
                "ttl_expired",
                None,
                sum(segment.est_tokens for segment in current),
                {"delta_s": round(delta, 3), "ttl_s": ttl_s},
            )
    return None


class DriftTracker:
    """Keep the last segment list and fingerprint per session."""

    def __init__(self, max_sessions: int = 256) -> None:
        self.max_sessions = max_sessions
        self._state: dict[str, tuple[list[Segment], float, str, str, str]] = {}

    def observe(
        self,
        session_id: str,
        segments: list[Segment],
        ts: float,
        *,
        params: str = "",
        config_hash: str = "",
        model: str = "",
        ttl_s: float = 300.0,
    ) -> DriftEvent | None:
        previous = self._state.get(session_id)
        event = detect_drift(
            previous[0] if previous else None,
            segments,
            previous_ts=previous[1] if previous else None,
            current_ts=ts,
            ttl_s=ttl_s,
            previous_params=previous[2] if previous else None,
            current_params=params,
            previous_config_hash=previous[3] if previous else None,
            current_config_hash=config_hash,
            previous_model=previous[4] if previous else None,
            current_model=model,
        )
        if len(self._state) >= self.max_sessions and session_id not in self._state:
            self._state.pop(next(iter(self._state)))
        self._state[session_id] = (segments, ts, params, config_hash, model)
        return event

    def clear(self) -> None:
        self._state.clear()


def _lost(previous: list[Segment], current: list[Segment], first: int) -> int:
    end = min(len(previous), len(current))
    if first >= end:
        return 0
    return sum(segment.est_tokens for segment in current[first:end])


__all__ = ["DriftCause", "DriftEvent", "DriftTracker", "detect_drift"]
