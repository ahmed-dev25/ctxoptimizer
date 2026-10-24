"""Drift, baseline simulation and waste detectors (P2-4/P2-5/P2-7/P2-8)."""

from __future__ import annotations

from hashlib import sha256

from ctxproxy.analysis.baseline import simulate
from ctxproxy.analysis.drift import DriftEvent, DriftTracker, detect_drift
from ctxproxy.analysis.segments import Segment
from ctxproxy.analysis.waste import (
    HashObservation,
    identical_outputs,
    recurring_drift,
    redundant_rereads,
    runaway_session,
    unbatched_fanout,
)


def _seg(kind: str, value: str, tokens: int, marker: bool = False) -> Segment:
    return Segment(
        kind=kind,  # type: ignore[arg-type]
        msg_index=None,
        block_index=None,
        hash=sha256(value.encode()).digest()[:8],
        est_tokens=tokens,
        has_marker=marker,
    )


def _base() -> list[Segment]:
    return [
        _seg("tool_def", "tools", 100),
        _seg("system", "system", 200, marker=True),
        _seg("message", "user", 50),
    ]


def test_drift_append_is_clean() -> None:
    previous = _base()
    current = [*previous, _seg("message", "assistant", 80)]
    assert detect_drift(previous, current, previous_ts=0, current_ts=1) is None


def test_drift_causes() -> None:
    previous = _base()
    tool_change = [_seg("tool_def", "new-tools", 100), *previous[1:]]
    assert detect_drift(previous, tool_change) is not None
    assert detect_drift(previous, tool_change).cause == "tools_changed"  # type: ignore[union-attr]
    system_change = [previous[0], _seg("system", "new-system", 200), previous[2]]
    assert detect_drift(previous, system_change).cause == "system_changed"  # type: ignore[union-attr]
    history_change = [*previous[:2], _seg("message", "edited", 50)]
    assert detect_drift(previous, history_change).cause == "history_mutated"  # type: ignore[union-attr]


def test_drift_params_config_model_and_ttl() -> None:
    previous = _base()
    assert (
        detect_drift(previous, previous, previous_params="a", current_params="b").cause
        == "params_changed"
    )  # type: ignore[union-attr]
    assert (
        detect_drift(previous, previous, previous_config_hash="a", current_config_hash="b").cause
        == "config_changed"
    )  # type: ignore[union-attr]
    assert (
        detect_drift(previous, previous, previous_model="a", current_model="b").cause
        == "model_switched"
    )  # type: ignore[union-attr]
    assert detect_drift(previous, previous, previous_ts=0, current_ts=400).cause == "ttl_expired"  # type: ignore[union-attr]


def test_drift_tracker_and_truncation() -> None:
    tracker = DriftTracker()
    assert tracker.observe("s", _base(), 0) is None
    assert tracker.observe("s", [*_base(), _seg("message", "next", 10)], 1) is None
    event = tracker.observe("s", [*_base()[:2], _seg("message", "changed", 10)], 2)
    assert event is not None and event.cause == "history_mutated"
    assert detect_drift(_base(), _base()[:2]) is not None


def test_baseline_explicit_read_write() -> None:
    previous = [_seg("system", "s", 100, marker=True), _seg("message", "u", 50)]
    current = [
        _seg("system", "s", 100, marker=True),
        _seg("message", "u", 50),
        _seg("message", "a", 20, marker=True),
    ]
    sim = simulate("explicit-anthropic", previous, 0, current, 1)
    assert sim.read_tokens == 100
    assert sim.write_5m_tokens == 70
    assert sim.fresh_tokens == 0


def test_baseline_no_marker_and_ttl() -> None:
    previous = [_seg("message", "u", 100)]
    current = [_seg("message", "u", 100)]
    assert simulate("explicit-anthropic", previous, 0, current, 1).read_tokens == 0
    assert simulate("explicit-anthropic", previous, 0, current, 400).read_tokens == 0


def test_baseline_implicit_minimum_prefix() -> None:
    previous = [_seg("message", "a", 1024), _seg("message", "b", 1024)]
    current = previous
    sim = simulate("implicit-openai", previous, 0, current, 1, min_prefix=1024)
    assert sim.read_tokens == 2048
    assert sim.fresh_tokens == 0
    short = [_seg("message", "a", 100)]
    assert simulate("implicit-openai", short, 0, short, 1).read_tokens == 0


def test_waste_w1_and_w2() -> None:
    prior = {b"h1": HashObservation(b"h1", tokens=500, turn=1, tool_name="Read")}
    current = [HashObservation(b"h1", tokens=500, turn=2, tool_name="Read")]
    w1 = redundant_rereads(current, prior, session_id="s", project="p", ts=10)
    assert len(w1) == 1
    assert w1[0].est_tokens_wasted == 500
    assert w1[0].detector == "redundant_reread"
    observations = [HashObservation(b"h2", tokens=300, turn=index) for index in range(3)]
    w2 = identical_outputs(observations, session_id="s", project="p", ts=10)
    assert len(w2) == 1
    assert w2[0].est_tokens_wasted == 600


def test_waste_w3_w4_w5() -> None:
    w3 = unbatched_fanout(
        [["read", "read", "read", "read"]],
        read_names={"read"},
        session_id="s",
        project="p",
        ts=10,
    )
    assert len(w3) == 1 and w3[0].detector == "unbatched_fanout"
    w4 = runaway_session(0, 1000, 8, session_id="s", project="p", tokens=400, idle_gap_s=900)
    assert w4 is not None and w4.est_tokens_wasted == 400
    events = [
        DriftEvent("system_changed", 1, 100, {}),
        DriftEvent("system_changed", 1, 200, {}),
    ]
    w5 = recurring_drift(events, session_id="s", project="p", ts=10)
    assert len(w5) == 1
    assert w5[0].est_tokens_wasted == 300
