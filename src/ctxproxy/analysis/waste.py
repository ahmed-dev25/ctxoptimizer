"""Deterministic waste detectors W1-W6 (SPEC section 13.6). Advisory only."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from ctxproxy.analysis.drift import DriftEvent
from ctxproxy.ids import new_ulid
from ctxproxy.models import WasteFinding


@dataclass(frozen=True, slots=True)
class HashObservation:
    hash: bytes
    tokens: int
    turn: int = 0
    tool_name: str | None = None


def redundant_rereads(
    current: list[HashObservation],
    prior: dict[bytes, HashObservation],
    *,
    session_id: str,
    project: str | None,
    ts: float,
) -> list[WasteFinding]:
    """W1: content re-read after an earlier turn in the same session."""
    findings: list[WasteFinding] = []
    seen: set[bytes] = set()
    for observation in current:
        if observation.hash not in prior or observation.hash in seen:
            continue
        seen.add(observation.hash)
        findings.append(
            _finding(
                "redundant_reread",
                observation,
                session_id,
                project,
                ts,
                occurrences=2,
                evidence={
                    "turn": observation.turn,
                    "first_seen_turn": prior[observation.hash].turn,
                    "tool": observation.tool_name,
                },
            )
        )
    return findings


def identical_outputs(
    observations: list[HashObservation],
    *,
    session_id: str,
    project: str | None,
    ts: float,
    min_occurrences: int = 3,
) -> list[WasteFinding]:
    """W2: the same tool output appears at least N times in one session."""
    grouped: dict[bytes, list[HashObservation]] = {}
    for observation in observations:
        grouped.setdefault(observation.hash, []).append(observation)
    findings: list[WasteFinding] = []
    for items in grouped.values():
        if len(items) < min_occurrences:
            continue
        tokens = items[0].tokens * (len(items) - 1)
        findings.append(
            _finding(
                "identical_output",
                items[0],
                session_id,
                project,
                ts,
                occurrences=len(items),
                evidence={"turns": [item.turn for item in items]},
                tokens=tokens,
            )
        )
    return findings


def unbatched_fanout(
    turns: list[list[str]],
    *,
    read_names: set[str],
    session_id: str,
    project: str | None,
    ts: float,
    min_calls: int = 4,
) -> list[WasteFinding]:
    """W3: many sequential read-like calls in one assistant turn."""
    findings: list[WasteFinding] = []
    for turn_index, names in enumerate(turns):
        reads = [name for name in names if name.lower() in read_names]
        if len(reads) < min_calls:
            continue
        findings.append(
            WasteFinding(
                finding_id=new_ulid(),
                ts=ts,
                session_id=session_id,
                project=project,
                detector="unbatched_fanout",
                key_hash=sha256(f"{turn_index}:{','.join(reads)}".encode()).digest()[:16],
                request_id=None,
                occurrences=1,
                first_seen_ts=ts,
                last_seen_ts=ts,
                evidence={"turn": turn_index, "calls": reads},
                est_tokens_wasted=0,
                est_cost_usd=None,
                status="new",
            )
        )
    return findings


def runaway_session(
    previous_ts: float | None,
    current_ts: float,
    turns: int,
    *,
    session_id: str,
    project: str | None,
    tokens: int,
    idle_gap_s: float = 900.0,
    min_turns: int = 6,
) -> WasteFinding | None:
    """W4: an active session resumes after a long idle gap."""
    if previous_ts is None or turns < min_turns:
        return None
    gap = current_ts - previous_ts
    if gap <= idle_gap_s:
        return None
    return WasteFinding(
        finding_id=new_ulid(),
        ts=current_ts,
        session_id=session_id,
        project=project,
        detector="runaway_session",
        key_hash=sha256(f"{session_id}:{int(gap)}".encode()).digest()[:16],
        request_id=None,
        occurrences=1,
        first_seen_ts=current_ts,
        last_seen_ts=current_ts,
        evidence={"gap_s": round(gap, 3), "turns": turns},
        est_tokens_wasted=tokens,
        est_cost_usd=None,
        status="new",
    )


def recurring_drift(
    events: list[DriftEvent],
    *,
    session_id: str,
    project: str | None,
    ts: float,
    min_occurrences: int = 2,
) -> list[WasteFinding]:
    """W5/W6: the same drift cause recurring in a session."""
    grouped: dict[str, list[DriftEvent]] = {}
    for event in events:
        grouped.setdefault(event.cause, []).append(event)
    findings: list[WasteFinding] = []
    for cause, items in grouped.items():
        if len(items) < min_occurrences:
            continue
        detector = (
            "params_drift" if cause in {"params_changed", "model_switched"} else "recurring_drift"
        )
        findings.append(
            WasteFinding(
                finding_id=new_ulid(),
                ts=ts,
                session_id=session_id,
                project=project,
                detector=detector,
                key_hash=sha256(f"{detector}:{cause}".encode()).digest()[:16],
                request_id=None,
                occurrences=len(items),
                first_seen_ts=ts,
                last_seen_ts=ts,
                evidence={"cause": cause, "events": len(items)},
                est_tokens_wasted=sum(item.est_tokens_lost for item in items),
                est_cost_usd=None,
                status="new",
            )
        )
    return findings


def _finding(
    detector: str,
    observation: HashObservation,
    session_id: str,
    project: str | None,
    ts: float,
    *,
    occurrences: int,
    evidence: dict[str, object],
    tokens: int | None = None,
) -> WasteFinding:
    return WasteFinding(
        finding_id=new_ulid(),
        ts=ts,
        session_id=session_id,
        project=project,
        detector=detector,
        key_hash=sha256(detector.encode() + observation.hash).digest()[:16],
        request_id=None,
        occurrences=occurrences,
        first_seen_ts=ts,
        last_seen_ts=ts,
        evidence=evidence,
        est_tokens_wasted=observation.tokens if tokens is None else tokens,
        est_cost_usd=None,
        status="new",
    )


__all__ = [
    "HashObservation",
    "identical_outputs",
    "recurring_drift",
    "redundant_rereads",
    "runaway_session",
    "unbatched_fanout",
]
