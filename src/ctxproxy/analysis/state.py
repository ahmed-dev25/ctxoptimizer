"""Per-session analysis state: drift + waste findings (P2 wiring)."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256

from ctxproxy.analysis.drift import DriftEvent, detect_drift
from ctxproxy.analysis.markers import MarkerQuality, marker_quality
from ctxproxy.analysis.segments import Segment
from ctxproxy.analysis.tokens import estimate_tokens
from ctxproxy.analysis.waste import (
    EditObservation,
    HashObservation,
    churn_edits,
    identical_outputs,
    recurring_drift,
    redundant_rereads,
    runaway_session,
    schema_bloat,
)
from ctxproxy.models import WasteFinding
from ctxproxy.transforms.ansi import clean as ansi_clean
from ctxproxy.transforms.progress import clean as progress_clean


@dataclass
class SessionState:
    hashes: dict[bytes, HashObservation] = field(default_factory=dict)
    observations: list[HashObservation] = field(default_factory=list)
    segments: list[Segment] | None = None
    last_ts: float | None = None
    turns: int = 0
    drift_events: list[DriftEvent] = field(default_factory=list)
    used_tools: set[str] = field(default_factory=set)
    last_edits: dict[str, EditObservation] = field(default_factory=dict)
    schema_reported: set[str] = field(default_factory=set)


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    drift: DriftEvent | None
    findings: list[WasteFinding]
    marker_quality: MarkerQuality


class AnalysisState:
    """Bounded in-memory analysis for the dashboard and CLI."""

    def __init__(self, max_sessions: int = 256, max_findings: int = 500) -> None:
        self.max_sessions = max_sessions
        self.max_findings = max_findings
        self._sessions: dict[str, SessionState] = {}
        self._findings: list[WasteFinding] = []

    def observe(
        self,
        *,
        session_id: str,
        project: str | None,
        ts: float,
        segments: list[Segment],
        observations: list[HashObservation],
        model: str,
        config_hash: str,
        ttl_s: float = 300.0,
        tool_schemas: list[tuple[str, int]] | None = None,
        used_tools: list[str] | None = None,
        edits: list[EditObservation] | None = None,
        churn_enabled: bool = False,
        schema_bloat_enabled: bool = True,
        schema_min_requests: int = 10,
    ) -> AnalysisResult:
        state = self._sessions.get(session_id)
        if state is None:
            if len(self._sessions) >= self.max_sessions:
                self._sessions.pop(next(iter(self._sessions)))
            state = SessionState()
            self._sessions[session_id] = state

        drift = detect_drift(
            state.segments,
            segments,
            previous_ts=state.last_ts,
            current_ts=ts,
            ttl_s=ttl_s,
            previous_params=model,
            current_params=model,
            previous_config_hash=config_hash,
            current_config_hash=config_hash,
            previous_model=model,
            current_model=model,
        )
        if drift is not None:
            state.drift_events.append(drift)

        findings: list[WasteFinding] = []
        findings.extend(
            redundant_rereads(
                observations, state.hashes, session_id=session_id, project=project, ts=ts
            )
        )
        findings.extend(
            identical_outputs(
                [*state.observations, *observations],
                session_id=session_id,
                project=project,
                ts=ts,
            )
        )
        runaway = runaway_session(
            state.last_ts,
            ts,
            state.turns,
            session_id=session_id,
            project=project,
            tokens=sum(item.tokens for item in observations),
        )
        if runaway is not None:
            findings.append(runaway)
        if drift is not None:
            findings.extend(
                recurring_drift(state.drift_events, session_id=session_id, project=project, ts=ts)
            )
        if used_tools:
            state.used_tools.update(used_tools)
        if schema_bloat_enabled and tool_schemas:
            request_count = state.turns + 1
            for name, tokens in tool_schemas:
                if name in state.used_tools or name in state.schema_reported:
                    continue
                bloat = schema_bloat(
                    name,
                    tokens,
                    request_count,
                    session_id=session_id,
                    project=project,
                    ts=ts,
                    min_requests=schema_min_requests,
                )
                if bloat is not None:
                    findings.append(bloat)
                    state.schema_reported.add(name)
        if churn_enabled and edits:
            findings.extend(
                churn_edits(
                    edits,
                    state.last_edits,
                    session_id=session_id,
                    project=project,
                    ts=ts,
                )
            )

        for observation in observations:
            state.hashes[observation.hash] = observation
        state.observations.extend(observations)
        state.observations = state.observations[-2000:]
        state.segments = segments
        state.last_ts = ts
        state.turns += 1
        self._findings.extend(findings)
        self._findings = self._findings[-self.max_findings :]
        return AnalysisResult(
            drift=drift,
            findings=findings,
            marker_quality=marker_quality(segments),
        )

    def findings(self) -> list[WasteFinding]:
        return list(self._findings)

    def clear(self) -> None:
        self._sessions.clear()
        self._findings.clear()


def observations_from_texts(
    texts: list[tuple[str | None, str | None, str]],
) -> list[HashObservation]:
    observations: list[HashObservation] = []
    for _tool_use_id, tool_name, text in texts:
        sigma = progress_clean(ansi_clean(text))
        observations.append(
            HashObservation(
                hash=sha256(sigma.encode("utf-8")).digest(),
                tokens=estimate_tokens(text),
                tool_name=tool_name,
            )
        )
    return observations


__all__ = [
    "AnalysisResult",
    "AnalysisState",
    "SessionState",
    "observations_from_texts",
]
