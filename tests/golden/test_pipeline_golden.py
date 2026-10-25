"""Committed golden pipeline cases (SPEC section 20.1)."""

from __future__ import annotations

import json
import tomllib

from ctxproxy.config import Config
from ctxproxy.models import Endpoint, Mode, Provider, RequestContext
from ctxproxy.pipeline import run_pipeline
from ctxproxy.providers import adapter_for
from ctxproxy.transforms import build_transforms


def _run(payload: dict, config_text: str) -> dict:
    raw = tomllib.loads(config_text) if config_text else {}
    raw.setdefault("mode", {})["default"] = "active"
    config = Config.model_validate(raw)
    adapter = adapter_for(Provider.ANTHROPIC, Endpoint.MESSAGES)
    ctx = RequestContext(
        request_id="golden",
        provider=Provider.ANTHROPIC,
        endpoint=Endpoint.MESSAGES,
        upstream_name="anthropic",
        model=str(payload.get("model") or "claude-sonnet-4-5"),
        stream=False,
        mode=Mode.ACTIVE,
        session_id="golden",
        project=None,
        client_name="golden",
        config=config,
        config_hash=config.config_hash,
        started_monotonic=0.0,
    )
    result = run_pipeline(ctx, payload, adapter, build_transforms(config), config)
    return {
        "payload": payload,
        "payload_json": json.dumps(payload, sort_keys=True),
        "original_tokens": result.orig_est_tokens,
        "final_tokens": result.final_est_tokens,
        "reports": [
            {
                "transform_id": report.transform_id,
                "changed": report.changed,
                "items_touched": report.items_touched,
                "tokens_before": report.est_tokens_before,
                "tokens_after": report.est_tokens_after,
                "discarded_reason": report.discarded_reason,
                "notes": report.notes,
            }
            for report in result.reports
        ],
    }


def test_golden_corpus(golden_root, golden_factory) -> None:
    runner = golden_factory(golden_root)
    cases = runner.cases()
    assert cases, "golden corpus is empty"
    for case in cases:
        runner.run(case, _run)
