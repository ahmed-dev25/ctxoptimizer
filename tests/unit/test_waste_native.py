"""W7 churn and W8 schema-bloat detectors plus edit extraction (P6-5)."""

from __future__ import annotations

from ctxproxy.analysis.edits import edit_observations
from ctxproxy.analysis.recommend import recommendations
from ctxproxy.analysis.segments import Segment
from ctxproxy.analysis.state import AnalysisState
from ctxproxy.analysis.waste import EditObservation, churn_edits
from ctxproxy.models import Provider, WasteFinding


def _segment(kind: str, tokens: int) -> Segment:
    return Segment(
        kind=kind,  # type: ignore[arg-type]
        msg_index=0,
        block_index=0,
        hash=b"0" * 8,
        est_tokens=tokens,
        has_marker=False,
    )


def test_schema_bloat_reports_unused_tool_once_at_threshold() -> None:
    state = AnalysisState()
    segments = [_segment("tool_def", 100), _segment("message", 50)]
    common = {
        "session_id": "s",
        "project": None,
        "segments": segments,
        "observations": [],
        "model": "gemini-2.5-pro",
        "config_hash": "h",
        "tool_schemas": [("unused", 100)],
        "schema_min_requests": 2,
    }
    first = state.observe(ts=1.0, **common)
    assert not [item for item in first.findings if item.detector == "schema_bloat"]
    second = state.observe(ts=2.0, **common)
    bloat = [item for item in second.findings if item.detector == "schema_bloat"]
    assert len(bloat) == 1
    assert bloat[0].est_tokens_wasted == 100
    third = state.observe(ts=3.0, **common)
    assert not [item for item in third.findings if item.detector == "schema_bloat"]


def test_schema_bloat_skips_used_tools() -> None:
    state = AnalysisState()
    result = state.observe(
        session_id="s",
        project=None,
        ts=1.0,
        segments=[_segment("tool_def", 100)],
        observations=[],
        model="",
        config_hash="h",
        tool_schemas=[("read", 100)],
        used_tools=["read"],
        schema_min_requests=1,
    )
    assert not [item for item in result.findings if item.detector == "schema_bloat"]


def test_churn_whitespace_and_revert() -> None:
    last: dict[str, EditObservation] = {}
    first = EditObservation("a.ts", "value", "value  ", tokens=4)
    findings = churn_edits([first], last, session_id="s", project=None, ts=1.0)
    assert findings[0].detector == "churn_detector"
    assert findings[0].evidence["kind"] == "whitespace_only"

    apply = EditObservation("b.ts", "A", "B", tokens=2)
    assert churn_edits([apply], last, session_id="s", project=None, ts=2.0) == []
    revert = EditObservation("b.ts", "B", "A", tokens=2)
    findings = churn_edits([revert], last, session_id="s", project=None, ts=3.0)
    assert findings[0].evidence["kind"] == "revert"


def test_edit_extraction_from_anthropic_and_openai() -> None:
    anthropic = {
        "messages": [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Edit",
                        "input": {
                            "file_path": "a.ts",
                            "old_string": "old",
                            "new_string": "new",
                        },
                    }
                ],
            }
        ]
    }
    observations = edit_observations(anthropic, Provider.ANTHROPIC)
    assert len(observations) == 1
    assert observations[0].path == "a.ts"
    assert observations[0].tokens > 0

    openai = {
        "input": [
            {
                "type": "function_call",
                "name": "apply_patch",
                "arguments": '{"path":"b.ts","old":"x","new":"y"}',
            }
        ]
    }
    observations = edit_observations(openai, Provider.OPENAI)
    assert observations[0].path == "b.ts"


def test_churn_is_opt_in_in_state() -> None:
    kwargs = {
        "session_id": "s",
        "project": None,
        "segments": [_segment("message", 10)],
        "observations": [],
        "model": "",
        "config_hash": "h",
    }
    disabled = AnalysisState()
    disabled.observe(
        ts=1.0,
        edits=[EditObservation("a.ts", "A", "B", tokens=5)],
        churn_enabled=False,
        **kwargs,
    )
    result = disabled.observe(
        ts=2.0,
        edits=[EditObservation("a.ts", "B", "A", tokens=5)],
        churn_enabled=False,
        **kwargs,
    )
    assert not [item for item in result.findings if item.detector == "churn_detector"]

    enabled = AnalysisState()
    enabled.observe(
        ts=1.0,
        edits=[EditObservation("a.ts", "A", "B", tokens=5)],
        churn_enabled=True,
        **kwargs,
    )
    result = enabled.observe(
        ts=2.0,
        edits=[EditObservation("a.ts", "B", "A", tokens=5)],
        churn_enabled=True,
        **kwargs,
    )
    assert [item for item in result.findings if item.detector == "churn_detector"]


def test_recommendations_include_schema_and_churn() -> None:
    findings = [
        WasteFinding(
            finding_id="1",
            ts=0.0,
            session_id="s",
            project=None,
            detector="schema_bloat",
            key_hash=b"0" * 16,
            request_id=None,
            occurrences=10,
            first_seen_ts=0.0,
            last_seen_ts=0.0,
            evidence={},
            est_tokens_wasted=900,
            est_cost_usd=None,
        ),
        WasteFinding(
            finding_id="2",
            ts=0.0,
            session_id="s",
            project=None,
            detector="churn_detector",
            key_hash=b"1" * 16,
            request_id=None,
            occurrences=1,
            first_seen_ts=0.0,
            last_seen_ts=0.0,
            evidence={},
            est_tokens_wasted=20,
            est_cost_usd=None,
        ),
    ]
    ids = {item["id"] for item in recommendations(findings)}
    assert {"prune_mcp_schemas", "investigate_churn"} <= ids
