"""Core enum and dataclass shapes (SPEC section 10)."""

from __future__ import annotations

from ctxproxy.config import Config
from ctxproxy.ids import new_ulid
from ctxproxy.models import (
    Endpoint,
    Mode,
    Provider,
    RequestContext,
    TransformReport,
    Usage,
)


def test_enums_serialize_as_strings() -> None:
    assert Provider.ANTHROPIC == "anthropic"
    assert Endpoint.PASSTHROUGH == "passthrough"
    assert Mode.SHADOW == "shadow"


def test_request_context_holds_config_snapshot() -> None:
    config = Config()
    context = RequestContext(
        request_id=new_ulid(),
        provider=Provider.ANTHROPIC,
        endpoint=Endpoint.MESSAGES,
        upstream_name="anthropic",
        model="claude-sonnet-4",
        stream=True,
        mode=Mode.SHADOW,
        session_id="session-1",
        project="ctxproxy",
        client_name="claude-code",
        config=config,
        config_hash=config.config_hash,
        started_monotonic=1.0,
    )
    assert context.provider is Provider.ANTHROPIC
    assert context.config_hash == config.config_hash


def test_usage_defaults_are_unknown() -> None:
    usage = Usage()
    assert usage.source == "none"
    assert usage.fresh_input is None
    assert usage.cache_read is None
    assert usage.assistant_text_hashes is None


def test_transform_report_uses_independent_note_dicts() -> None:
    first = TransformReport(transform_id="ansi_strip")
    second = TransformReport(transform_id="line_dedupe")
    first.notes["touched"] = 1
    assert second.notes == {}
    assert first.changed is False
