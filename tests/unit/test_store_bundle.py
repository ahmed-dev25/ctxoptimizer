"""Persisted reports, findings, drift and captures for the dashboard (P5)."""

from __future__ import annotations

import time
from pathlib import Path

from ctxproxy.analysis.drift import DriftEvent
from ctxproxy.models import TransformReport, WasteFinding
from ctxproxy.telemetry.store import Store


def test_store_persists_request_bundle(tmp_path: Path) -> None:
    store = Store(tmp_path / "ctxproxy.db")
    finding = WasteFinding(
        finding_id="f1",
        ts=time.time(),
        session_id="s1",
        project="p",
        detector="redundant_reread",
        key_hash=b"k" * 16,
        request_id="r1",
        occurrences=2,
        first_seen_ts=time.time(),
        last_seen_ts=time.time(),
        evidence={"turn": 1},
        est_tokens_wasted=10,
        est_cost_usd=None,
    )
    store.record_request(
        {
            "request_id": "r1",
            "ts": time.time(),
            "session_id": "s1",
            "provider": "openai",
            "endpoint": "chat",
            "mode": "shadow",
            "_transform_reports": [
                TransformReport(
                    transform_id="ansi_strip",
                    ran=True,
                    changed=True,
                    est_tokens_before=100,
                    est_tokens_after=90,
                    duration_ms=1.5,
                )
            ],
            "_drift": DriftEvent("system_changed", 1, 20, {"kind": "system"}),
            "_findings": [finding],
            "_captures": [
                {
                    "transform_id": None,
                    "location": "block-0",
                    "before_hash": "a" * 64,
                    "after_hash": "b" * 64,
                }
            ],
        }
    )
    store.flush()
    assert store.fetch_transform_reports("r1")[0]["est_tokens_saved"] == 10
    assert store.fetch_drift()[0]["cause"] == "system_changed"
    assert store.fetch_waste()[0]["finding_id"] == "f1"
    assert store.fetch_captures("r1")[0]["location"] == "block-0"
    assert store.transform_stats()[0]["tokens_saved"] == 10
    assert store.set_waste_status("f1", "ack") is True
    assert store.fetch_waste(status="ack")[0]["finding_id"] == "f1"
    store.close()
