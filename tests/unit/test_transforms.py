"""Core transforms: ANSI, progress, whitespace, dedupe, truncate, backref."""

from __future__ import annotations

from typing import Any

from ctxproxy.config import Config
from ctxproxy.models import Endpoint, Mode, Provider, RequestContext
from ctxproxy.providers import adapter_for
from ctxproxy.transforms import (
    ansi,
    build_transforms,
    dedupe_lines,
    progress,
    truncate,
    whitespace,
)
from ctxproxy.transforms.backref import DuplicateBackref
from ctxproxy.transforms.base import TextTransform


def test_ansi_strip() -> None:
    raw = "\x1b[31mred\x1b[0m \x1b]0;title\x07ok\n\x00next"
    out = ansi.clean(raw)
    assert out == "red ok\nnext"
    assert ansi.clean(out) == out


def test_progress_collapse() -> None:
    bars = [f"{'#' * 20} {index}%" for index in range(4)]
    raw = "\n".join(["start", *bars, "error: boom", "done"])
    out = progress.clean(raw)
    assert "[ctxproxy: 4 progress updates collapsed]" in out
    assert "error: boom" in out
    assert out.rstrip().endswith("done")
    assert progress.clean(out) == out


def test_carriage_return_keeps_last_segment() -> None:
    assert progress.clean("10%\r50%\r100%\ndone") == "100%\ndone"


def test_whitespace_trim() -> None:
    raw = "  a  \n\n\n\n  b\n\n"
    out = whitespace.clean(raw, max_blank_run=2)
    assert out == "  a\n\n\n  b\n"
    assert whitespace.clean(out, max_blank_run=2) == out


def test_exact_dedupe() -> None:
    raw = "\n".join(["same"] * 5)
    out = dedupe_lines.clean(raw, min_repeat=3)
    assert "[ctxproxy: line repeated 4 more times]" in out
    assert dedupe_lines.clean(out, min_repeat=3) == out


def test_near_duplicate_dedupe() -> None:
    raw = "\n".join(f"step {index}" for index in range(1, 7))
    out = dedupe_lines.clean(raw, min_repeat=3)
    assert "step 1" in out and "step 6" in out
    assert "4 similar lines omitted" in out
    assert dedupe_lines.clean(out, min_repeat=3) == out


def test_dedupe_leaves_signal_lines() -> None:
    raw = "\n".join(["ERROR one", "ERROR two", "ERROR three", "ERROR four"])
    out = dedupe_lines.clean(raw, min_repeat=2)
    assert "similar lines omitted" not in out


def _truncate_config() -> Config:
    base = Config()
    truncate_cfg = base.transforms.smart_truncate.model_copy(
        update={
            "trigger_bytes": 500,
            "target_bytes": 300,
            "head_lines": 5,
            "tail_lines": 5,
            "context_lines": 1,
            "max_signal_lines": 10,
            "max_line_chars": 200,
        }
    )
    return base.model_copy(
        update={"transforms": base.transforms.model_copy(update={"smart_truncate": truncate_cfg})}
    )


def test_truncate_keeps_signals_and_summary() -> None:
    config = _truncate_config()
    lines = [f"line {index}" for index in range(100)]
    lines[50] = "ERROR: boom"
    lines[-1] = "1 failed, 99 passed"
    raw = "\n".join(lines)
    out = truncate.clean(raw, config.transforms.smart_truncate)
    assert "line 0" in out
    assert "line 98" in out
    assert "ERROR: boom" in out
    assert "1 failed, 99 passed" in out
    assert "[ctxproxy:" in out and "omitted; ref=" in out
    assert len(out.encode("utf-8")) <= 450
    assert truncate.clean(out, config.transforms.smart_truncate) == out


def test_truncate_skips_nul_bytes() -> None:
    config = _truncate_config()
    raw = "\x00" + "x" * 2000
    assert truncate.clean(raw, config.transforms.smart_truncate) == raw


def _ctx(config: Config) -> RequestContext:
    return RequestContext(
        request_id="req",
        provider=Provider.ANTHROPIC,
        endpoint=Endpoint.MESSAGES,
        upstream_name="anthropic",
        model="claude-sonnet-4-5",
        stream=False,
        mode=Mode.ACTIVE,
        session_id="s",
        project=None,
        client_name="test",
        config=config,
        config_hash=config.config_hash,
        started_monotonic=0.0,
    )


def _backref_payload() -> dict[str, Any]:
    content = "identical output " * 200
    return {
        "model": "claude-sonnet-4-5",
        "messages": [
            {"role": "user", "content": "go"},
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "Bash", "input": {}},
                    {"type": "tool_use", "id": "t2", "name": "Bash", "input": {}},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "t1", "content": content},
                    {"type": "tool_result", "tool_use_id": "t2", "content": content},
                ],
            },
        ],
    }


def test_duplicate_backref_changes_only_later_copy() -> None:
    config = Config.model_validate({"transforms": {"duplicate_backref": {"min_bytes": 100}}})
    payload = _backref_payload()
    adapter = adapter_for(Provider.ANTHROPIC, Endpoint.MESSAGES)
    report = DuplicateBackref().apply(_ctx(config), payload, adapter, config)
    assert report.changed is True
    first, second = payload["messages"][2]["content"]
    assert first["content"].startswith("identical output")
    assert second["content"].startswith("[ctxproxy: output identical")
    assert "t1" in second["content"]
    assert DuplicateBackref().apply(_ctx(config), payload, adapter, config).changed is False


def test_build_transforms_order() -> None:
    names = [transform.id for transform in build_transforms(Config())]
    assert names == [
        "ansi_strip",
        "progress_collapse",
        "line_dedupe",
        "whitespace_trim",
        "smart_truncate",
        "duplicate_backref",
        "anthropic_cache",
    ]


def test_text_transform_respects_eligibility() -> None:
    config = Config()
    payload = _backref_payload()
    adapter = adapter_for(Provider.ANTHROPIC, Endpoint.MESSAGES)
    transform = TextTransform("shrink", lambda text: "short", eligible=lambda ref: False)
    report = transform.apply(_ctx(config), payload, adapter, config)
    assert report.changed is False
