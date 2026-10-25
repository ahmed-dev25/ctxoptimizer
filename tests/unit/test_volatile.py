"""Volatile-token normalizer (SPEC 12.11)."""

from __future__ import annotations

from ctxproxy.config import Config
from ctxproxy.models import Endpoint, Mode, Provider, RequestContext
from ctxproxy.providers import adapter_for
from ctxproxy.transforms import build_transforms
from ctxproxy.transforms.volatile import (
    VolatileNormalizer,
    normalize_system,
    normalize_user_env,
)


def _config(enabled: bool = True) -> Config:
    return Config.model_validate({"transforms": {"volatile_normalizer": {"enabled": enabled}}})


def _ctx(config: Config) -> RequestContext:
    return RequestContext(
        request_id="r",
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


def test_normalizes_dates_uuids_and_time() -> None:
    text = (
        "Today's date: 2026-10-25T13:05:11Z\n"
        "id=550e8400-e29b-41d4-a716-446655440000\n"
        "Current time: 13:05:11\n"
    )
    result = normalize_system(text)
    assert "2026-10-25" in result
    assert "T13:05:11" not in result
    assert "[uuid]" in result
    assert "[time omitted]" in result


def test_user_env_only_is_touched() -> None:
    outside = "do not touch 2026-10-25T13:05:11Z 1700000000"
    inside = "<env>\nToday's date: 2026-10-25T13:05:11Z\nepoch 1700000000\n</env>"
    assert normalize_user_env(outside) == outside
    changed = normalize_user_env(inside)
    assert "T13:05:11" not in changed
    assert "1700000000" not in changed
    assert "[epoch]" in changed


def test_transform_mutates_system_and_user_env_but_not_plain_user_text() -> None:
    config = _config()
    adapter = adapter_for(Provider.ANTHROPIC, Endpoint.MESSAGES)
    payload = {
        "system": "Today's date: 2026-10-25T13:05:11Z",
        "messages": [
            {"role": "user", "content": "normal user text 2026-10-25T13:05:11Z"},
            {
                "role": "user",
                "content": "<env>epoch 1700000000</env>",
            },
        ],
    }
    report = VolatileNormalizer().apply(_ctx(config), payload, adapter, config)
    assert report.changed is True
    assert payload["system"] == "Today's date: 2026-10-25"
    assert payload["messages"][0]["content"] == "normal user text 2026-10-25T13:05:11Z"
    assert payload["messages"][1]["content"] == "<env>epoch [epoch]</env>"
    second = VolatileNormalizer().apply(_ctx(config), payload, adapter, config)
    assert second.changed is False


def test_registry_includes_volatile_when_enabled() -> None:
    assert "volatile_normalizer" in [t.id for t in build_transforms(_config())]
    assert "volatile_normalizer" not in [t.id for t in build_transforms(_config(False))]
