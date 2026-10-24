"""Config precedence, validation and hashing (SPEC section 7)."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from pydantic import ValidationError

from ctxproxy.config import (
    Config,
    compute_config_hash,
    data_dir,
    default_config_text,
    ensure_config_file,
    load_config,
    resolve_config_path,
    unknown_keys,
)


def test_defaults_match_spec() -> None:
    config = Config()
    assert config.server.host == "127.0.0.1"
    assert config.server.port == 8787
    assert config.mode.default == "shadow"
    assert config.telemetry.capture_payloads == "changed_blocks"
    assert config.transforms.ansi_strip.enabled is True
    assert config.transforms.cache_serve.enabled is False
    assert config.transforms.duplicate_backref.include_never_touch is True
    assert config.guard.auto_reenable == 0
    assert config.guard.expand_error_rate == pytest.approx(0.20)
    assert config.waste.schema_bloat.enabled is True


def test_default_template_matches_model_defaults() -> None:
    raw = tomllib.loads(default_config_text())
    assert Config.model_validate(raw) == Config()


def test_precedence_cli_over_env_over_file(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        '[server]\nport = 9001\n\n[mode]\ndefault = "active"\n',
        encoding="utf-8",
    )
    env = {"CTXPROXY_PORT": "9002", "CTXPROXY_MODE": "passthrough"}
    config = load_config(
        path=config_file,
        env=env,
        overrides={"server.port": 9003},
    )
    assert config.server.port == 9003
    assert config.mode.default == "passthrough"


def test_env_overrides_file(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text("[server]\nport = 9001\n", encoding="utf-8")
    config = load_config(path=config_file, env={"CTXPROXY_PORT": "9002"})
    assert config.server.port == 9002


def test_file_used_when_present(tmp_path: Path) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text("[server]\nport = 9001\n", encoding="utf-8")
    config = load_config(path=config_file, env={})
    assert config.server.port == 9001


def test_missing_explicit_config_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_config(path=tmp_path / "absent.toml", env={})


def test_env_upstream_override(tmp_path: Path) -> None:
    config_file = tmp_path / "empty.toml"
    config_file.write_text("", encoding="utf-8")
    config = load_config(
        path=config_file,
        env={"CTXPROXY_UPSTREAM_OPENROUTER": "https://openrouter.ai/api"},
    )
    assert config.upstreams["openrouter"] == "https://openrouter.ai/api"


def test_resolve_config_path_prefers_explicit(tmp_path: Path) -> None:
    explicit = tmp_path / "a.toml"
    from_env = tmp_path / "b.toml"
    env = {"CTXPROXY_CONFIG": str(from_env)}
    assert resolve_config_path(explicit, env) == explicit
    assert resolve_config_path(None, env) == from_env


def test_invalid_port_rejected() -> None:
    with pytest.raises(ValidationError):
        Config.model_validate({"server": {"port": 70000}})


def test_remote_requires_admin_token() -> None:
    with pytest.raises(ValidationError):
        Config.model_validate({"server": {"allow_remote": True}})


def test_non_loopback_requires_remote() -> None:
    with pytest.raises(ValidationError):
        Config.model_validate({"server": {"host": "0.0.0.0"}})
    allowed = Config.model_validate(
        {"server": {"host": "0.0.0.0", "allow_remote": True, "admin_token": "test-token"}}
    )
    assert allowed.server.allow_remote is True


def test_truncate_budget_invariant() -> None:
    with pytest.raises(ValidationError):
        Config.model_validate(
            {"transforms": {"smart_truncate": {"trigger_bytes": 1000, "target_bytes": 800}}}
        )


def test_cache_serve_requires_capture() -> None:
    with pytest.raises(ValidationError):
        Config.model_validate(
            {
                "transforms": {"cache_serve": {"enabled": True}},
                "telemetry": {"capture_payloads": "off"},
            }
        )


def test_upstream_url_scheme_rejected() -> None:
    with pytest.raises(ValidationError):
        Config.model_validate({"upstreams": {"bad": "ftp://example.com"}})


def test_config_hash_is_stable_and_scoped() -> None:
    base = Config()
    assert base.config_hash == compute_config_hash(Config())

    server = base.server.model_copy(update={"port": 9999})
    assert base.model_copy(update={"server": server}).config_hash == base.config_hash

    truncate = base.transforms.smart_truncate.model_copy(update={"target_bytes": 8192})
    transforms = base.transforms.model_copy(update={"smart_truncate": truncate})
    changed = base.model_copy(update={"transforms": transforms})
    assert changed.config_hash != base.config_hash


def test_unknown_keys_reports_dotted_paths() -> None:
    raw = tomllib.loads("[server]\nport = 8787\nbogus = 1\n\n[nope]\nx = 1\n")
    assert unknown_keys(raw) == ["server.bogus", "nope"]


def test_ensure_config_file_creates_and_is_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "config.toml"
    assert ensure_config_file(target) is True
    assert target.exists()
    assert ensure_config_file(target) is False
    parsed = tomllib.loads(target.read_text(encoding="utf-8"))
    assert Config.model_validate(parsed) == Config()


def test_data_dir_env_override(tmp_path: Path) -> None:
    assert data_dir({"CTXPROXY_DATA_DIR": str(tmp_path)}) == tmp_path
