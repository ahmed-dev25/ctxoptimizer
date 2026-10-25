"""Per-session analysis state wiring (P2)."""

from __future__ import annotations

from hashlib import sha256

from ctxoptimizer.analysis.segments import Segment
from ctxoptimizer.analysis.state import AnalysisState, observations_from_texts
from ctxoptimizer.analysis.waste import HashObservation


def _seg(value: str, tokens: int) -> Segment:
    return Segment(
        kind="system",
        msg_index=None,
        block_index=None,
        hash=sha256(value.encode()).digest()[:8],
        est_tokens=tokens,
        has_marker=False,
    )


def _obs(value: bytes, tokens: int) -> HashObservation:
    return HashObservation(hash=value, tokens=tokens, tool_name="Bash")


def test_observations_from_texts_is_stable() -> None:
    first = observations_from_texts([("t1", "Bash", "hello world")])
    second = observations_from_texts([("t1", "Bash", "hello world")])
    assert first[0].hash == second[0].hash
    assert first[0].tokens == second[0].tokens


def test_redundant_reread_on_second_turn() -> None:
    state = AnalysisState()
    first = state.observe(
        session_id="s",
        project="p",
        ts=1.0,
        segments=[_seg("a", 100)],
        observations=[_obs(b"h1", 100)],
        model="m",
        config_hash="c",
    )
    assert first.findings == []
    second = state.observe(
        session_id="s",
        project="p",
        ts=2.0,
        segments=[_seg("a", 100)],
        observations=[_obs(b"h1", 100)],
        model="m",
        config_hash="c",
    )
    assert any(f.detector == "redundant_reread" for f in second.findings)
    assert state.findings()


def test_identical_output_and_drift_recurrence() -> None:
    state = AnalysisState()
    for index in range(3):
        state.observe(
            session_id="s",
            project="p",
            ts=float(index),
            segments=[_seg("a", 100)],
            observations=[_obs(b"same", 100)],
            model="m",
            config_hash="c",
        )
    detectors = {finding.detector for finding in state.findings()}
    assert "identical_output" in detectors
    assert "redundant_reread" in detectors

    for index in range(3):
        state.observe(
            session_id="t",
            project="p",
            ts=10.0 + index,
            segments=[_seg(f"system-{index}", 100)],
            observations=[],
            model="m",
            config_hash="c",
        )
    assert any(finding.detector == "recurring_drift" for finding in state.findings())
