"""Pipeline journal, no-regress and budget behavior (P2-3)."""

from __future__ import annotations

import time
from typing import Any

from ctxoptimizer.config import Config
from ctxoptimizer.models import Endpoint, Mode, Provider, RequestContext, TransformReport
from ctxoptimizer.pipeline import run_pipeline
from ctxoptimizer.providers import adapter_for
from ctxoptimizer.transforms.base import TextTransform


def _payload() -> dict[str, Any]:
    return {
        "model": "claude-sonnet-4-5",
        "messages": [
            {"role": "user", "content": "go"},
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_1",
                        "content": "hello world " * 20,
                    }
                ],
            },
        ],
    }


def _ctx(config: Config, mode: Mode = Mode.SHADOW) -> RequestContext:
    return RequestContext(
        request_id="req",
        provider=Provider.ANTHROPIC,
        endpoint=Endpoint.MESSAGES,
        upstream_name="anthropic",
        model="claude-sonnet-4-5",
        stream=False,
        mode=mode,
        session_id="session",
        project="proj",
        client_name="test",
        config=config,
        config_hash=config.config_hash,
        started_monotonic=0.0,
    )


class _Boom:
    id = "boom"

    def applies(self, ctx, payload, adapter) -> bool:
        return True

    def apply(self, ctx, payload, adapter, config) -> TransformReport:
        raise RuntimeError("boom")


class _Slow:
    id = "slow"

    def applies(self, ctx, payload, adapter) -> bool:
        return True

    def apply(self, ctx, payload, adapter, config) -> TransformReport:
        time.sleep(0.02)
        return TransformReport(transform_id=self.id, ran=True)


def test_transform_reduces_payload() -> None:
    config = Config.model_validate({"pipeline": {"min_saving_tokens": 1}})
    adapter = adapter_for(Provider.ANTHROPIC, Endpoint.MESSAGES)
    payload = _payload()
    result = run_pipeline(
        _ctx(config),
        payload,
        adapter,
        [TextTransform("shrink", lambda text: text.replace("hello world", "hi"))],
        config,
    )
    assert result.changed is True
    assert result.shadow is True
    assert result.final_est_tokens < result.orig_est_tokens
    assert "hello world" not in str(payload)


def test_no_regress_reverts_growth() -> None:
    config = Config.model_validate({"pipeline": {"min_saving_tokens": 5}})
    adapter = adapter_for(Provider.ANTHROPIC, Endpoint.MESSAGES)
    payload = _payload()
    original = payload["messages"][1]["content"][0]["content"]
    result = run_pipeline(
        _ctx(config),
        payload,
        adapter,
        [TextTransform("grow", lambda text: text + " extra")],
        config,
    )
    report = result.reports[0]
    assert report.discarded_reason == "no_regress"
    assert report.changed is False
    assert payload["messages"][1]["content"][0]["content"] == original


def test_exception_reverts_and_continues() -> None:
    config = Config.model_validate({"pipeline": {"min_saving_tokens": 1}})
    adapter = adapter_for(Provider.ANTHROPIC, Endpoint.MESSAGES)
    payload = _payload()
    original = payload["messages"][1]["content"][0]["content"]
    result = run_pipeline(
        _ctx(config),
        payload,
        adapter,
        [
            _Boom(),
            TextTransform("shrink", lambda text: text.replace("hello world", "hi")),
        ],
        config,
    )
    assert result.reports[0].discarded_reason == "error"
    assert result.changed is True
    assert payload["messages"][1]["content"][0]["content"].startswith("hi")
    assert original != payload["messages"][1]["content"][0]["content"]


def test_budget_skips_remaining() -> None:
    config = Config.model_validate({"pipeline": {"min_saving_tokens": 1, "time_budget_ms": 1}})
    adapter = adapter_for(Provider.ANTHROPIC, Endpoint.MESSAGES)
    result = run_pipeline(
        _ctx(config),
        _payload(),
        adapter,
        [_Slow(), TextTransform("shrink", lambda text: text)],
        config,
    )
    assert result.reports[1].discarded_reason == "budget"
    assert result.reports[1].ran is False


def test_non_applicable_transform_is_skipped() -> None:
    config = Config.model_validate({"pipeline": {"min_saving_tokens": 1}})
    adapter = adapter_for(Provider.ANTHROPIC, Endpoint.MESSAGES)
    result = run_pipeline(
        _ctx(config),
        _payload(),
        adapter,
        [TextTransform("off", lambda text: text, enabled=False)],
        config,
    )
    assert result.reports == []
    assert result.changed is False
