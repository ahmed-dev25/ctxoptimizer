"""Configuration loading and validation (SPEC section 7).

Precedence is CLI overrides > ``CTXPROXY_*`` environment > config file >
defaults. The models are frozen so a request always sees one immutable snapshot;
hot reload builds a new :class:`Config` instead of mutating the old one.

``config_hash`` covers only the settings that change forwarded bytes
(transforms, tool eligibility and pipeline policy), per SPEC section 7.1.
"""

from __future__ import annotations

import json
import logging
import os
import tomllib
from collections.abc import Mapping
from hashlib import sha256
from importlib import resources
from pathlib import Path
from typing import Any, Literal

import platformdirs
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Mode = Literal["passthrough", "shadow", "active"]
CaptureMode = Literal["off", "changed_blocks", "full"]
UpstreamKind = Literal["anthropic", "openai", "gemini", "ollama"]
UsageStyle = Literal[
    "anthropic",
    "openai",
    "deepseek",
    "openrouter",
    "gemini",
    "gemini-openai",
    "ollama",
    "ollama-openai",
]
CachePolicy = Literal[
    "explicit-anthropic",
    "implicit-openai",
    "automatic-deepseek",
    "gemini-implicit",
    "none",
]
CostSource = Literal["pricing", "provider", "none"]
ShellKind = Literal["bash", "zsh", "fish", "powershell"]

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
ENV_PREFIX = "CTXPROXY_"
CONFIG_RESOURCE = "default_config.toml"
logger = logging.getLogger(__name__)

_ENV_FIELDS = {
    "CTXPROXY_HOST": "server.host",
    "CTXPROXY_PORT": "server.port",
    "CTXPROXY_MODE": "mode.default",
    "CTXPROXY_LOG_LEVEL": "server.log_level",
    "CTXPROXY_UPDATE_MANIFEST": "update.manifest_url",
    "CTXPROXY_UPDATE_PUBLIC_KEY": "update.public_key",
}


class _Section(BaseModel):
    """Base for every config section: immutable and tolerant of new keys."""

    model_config = ConfigDict(extra="ignore", frozen=True)


class ServerConfig(_Section):
    host: str = "127.0.0.1"
    port: int = Field(default=8787, ge=1, le=65535)
    allow_remote: bool = False
    admin_token: str = ""
    max_body_bytes: int = Field(default=33554432, gt=0)
    log_level: str = "info"

    @model_validator(mode="after")
    def _check_binding(self) -> ServerConfig:
        if self.allow_remote:
            if not self.admin_token:
                raise ValueError("server.admin_token is required when allow_remote = true")
        elif self.host not in LOOPBACK_HOSTS:
            raise ValueError("server.host must be loopback unless allow_remote = true")
        return self


class ModeSettings(_Section):
    default: Mode = "shadow"


class UpstreamEntry(_Section):
    url: str
    kind: UpstreamKind
    usage: UsageStyle | None = None
    cache_policy: CachePolicy | None = None
    cost_source: CostSource | None = None
    cache_hints: bool | None = None
    inject_stream_usage: bool | None = None
    pricing_provider: str | None = None

    @field_validator("url")
    @classmethod
    def _check_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("upstream url must start with http:// or https://")
        return value


class HttpConfig(_Section):
    connect_timeout_s: float = Field(default=10, gt=0)
    write_timeout_s: float = Field(default=60, gt=0)
    pool_timeout_s: float = Field(default=30, gt=0)
    read_timeout_s: float = Field(default=0, ge=0)
    http2: bool = True
    max_connections: int = Field(default=100, gt=0)
    force_identity_encoding: bool = True


class PipelineConfig(_Section):
    time_budget_ms: int = Field(default=250, gt=0)
    offload_threshold_bytes: int = Field(default=262144, gt=0)
    min_saving_tokens: int = Field(default=20, ge=0)
    retry_original_on_status: list[int] = Field(default_factory=lambda: [400, 422])


class AnsiStripConfig(_Section):
    enabled: bool = True


class ProgressCollapseConfig(_Section):
    enabled: bool = True


class LineDedupeConfig(_Section):
    enabled: bool = True
    min_repeat: int = Field(default=3, ge=2)


class WhitespaceTrimConfig(_Section):
    enabled: bool = True
    max_blank_run: int = Field(default=2, ge=1)


class SmartTruncateConfig(_Section):
    enabled: bool = True
    trigger_bytes: int = Field(default=16384, gt=0)
    target_bytes: int = Field(default=10240, gt=0)
    head_lines: int = Field(default=40, ge=0)
    tail_lines: int = Field(default=60, ge=0)
    context_lines: int = Field(default=3, ge=0)
    max_line_chars: int = Field(default=2000, gt=0)
    max_signal_lines: int = Field(default=150, ge=1)


class DuplicateBackrefConfig(_Section):
    enabled: bool = True
    min_bytes: int = Field(default=2048, ge=0)
    include_never_touch: bool = True


class StaleResultElisionConfig(_Section):
    enabled: bool = False
    keep_recent_turns: int = Field(default=12, ge=0)
    batch_turns: int = Field(default=8, ge=1)
    min_bytes: int = Field(default=4096, ge=0)


class AnthropicCacheConfig(_Section):
    enabled: bool = True
    ttl: Literal["5m", "1h"] = "5m"
    respect_existing: bool = True
    max_breakpoints: int = Field(default=4, ge=1, le=4)


class OpenaiHintsConfig(_Section):
    enabled: bool = False
    send_prompt_cache_key: bool = True
    inject_stream_usage: bool = False


class CacheServeConfig(_Section):
    enabled: bool = False
    include_never_touch: bool = True
    min_bytes: int = Field(default=2048, ge=0)
    max_stubs_per_request: int = Field(default=6, ge=0)
    batch_turns: int = Field(default=8, ge=1)
    keep_recent_turns: int = Field(default=12, ge=0)
    max_state_sessions: int = Field(default=256, ge=1)
    max_entries_per_session: int = Field(default=512, ge=1)


class VolatileNormalizerConfig(_Section):
    enabled: bool = False


class TransformsConfig(_Section):
    ansi_strip: AnsiStripConfig = Field(default_factory=AnsiStripConfig)
    progress_collapse: ProgressCollapseConfig = Field(default_factory=ProgressCollapseConfig)
    line_dedupe: LineDedupeConfig = Field(default_factory=LineDedupeConfig)
    whitespace_trim: WhitespaceTrimConfig = Field(default_factory=WhitespaceTrimConfig)
    smart_truncate: SmartTruncateConfig = Field(default_factory=SmartTruncateConfig)
    duplicate_backref: DuplicateBackrefConfig = Field(default_factory=DuplicateBackrefConfig)
    stale_result_elision: StaleResultElisionConfig = Field(default_factory=StaleResultElisionConfig)
    anthropic_cache: AnthropicCacheConfig = Field(default_factory=AnthropicCacheConfig)
    openai_hints: OpenaiHintsConfig = Field(default_factory=OpenaiHintsConfig)
    cache_serve: CacheServeConfig = Field(default_factory=CacheServeConfig)
    volatile_normalizer: VolatileNormalizerConfig = Field(default_factory=VolatileNormalizerConfig)


class ToolsConfig(_Section):
    compactable: list[str] = Field(
        default_factory=lambda: [
            "*bash*",
            "*shell*",
            "*terminal*",
            "*exec*",
            "*run*",
            "*command*",
            "*test*",
            "*build*",
            "*npm*",
            "*pytest*",
            "*cargo*",
        ]
    )
    never_touch: list[str] = Field(
        default_factory=lambda: [
            "*read*",
            "*view*",
            "*cat*",
            "*edit*",
            "*write*",
            "*patch*",
            "*apply*",
            "*notebook*",
        ]
    )


class TelemetryConfig(_Section):
    db_path: str = ""
    capture_payloads: CaptureMode = "changed_blocks"
    retention_days: int = Field(default=14, ge=1)
    redact_secrets: bool = True
    writer_queue_max: int = Field(default=10000, ge=1)
    max_blob_bytes: int = Field(default=524288000, ge=0)


class RedundantRereadConfig(_Section):
    enabled: bool = True
    min_bytes: int = Field(default=512, ge=0)


class IdenticalOutputConfig(_Section):
    enabled: bool = True
    min_bytes: int = Field(default=1024, ge=0)


class UnbatchedFanoutConfig(_Section):
    enabled: bool = True
    min_calls: int = Field(default=4, ge=2)


class RunawaySessionConfig(_Section):
    enabled: bool = True
    idle_gap_s: int = Field(default=900, ge=0)
    min_turns: int = Field(default=6, ge=1)


class RecurringDriftConfig(_Section):
    enabled: bool = True
    min_occurrences: int = Field(default=2, ge=1)


class ChurnDetectorConfig(_Section):
    enabled: bool = False


class SchemaBloatConfig(_Section):
    enabled: bool = True
    min_session_requests: int = Field(default=10, ge=1)


class WasteConfig(_Section):
    enabled: bool = True
    dedupe_window_min: int = Field(default=30, ge=0)
    capture_assistant_hashes: bool = True
    redundant_reread: RedundantRereadConfig = Field(default_factory=RedundantRereadConfig)
    identical_output: IdenticalOutputConfig = Field(default_factory=IdenticalOutputConfig)
    unbatched_fanout: UnbatchedFanoutConfig = Field(default_factory=UnbatchedFanoutConfig)
    runaway_session: RunawaySessionConfig = Field(default_factory=RunawaySessionConfig)
    recurring_drift: RecurringDriftConfig = Field(default_factory=RecurringDriftConfig)
    churn_detector: ChurnDetectorConfig = Field(default_factory=ChurnDetectorConfig)
    schema_bloat: SchemaBloatConfig = Field(default_factory=SchemaBloatConfig)


class GuardConfig(_Section):
    enabled: bool = True
    fallback_window: int = Field(default=50, ge=1)
    fallback_limit: int = Field(default=3, ge=0)
    our_fault_drift_limit: int = Field(default=1, ge=0)
    min_savings_to_stay: float = Field(default=0.01, ge=0)
    notify: Literal["dashboard", "dashboard+banner"] = "dashboard"
    auto_reenable: int = Field(default=0, ge=0)
    expand_error_rate: float = Field(default=0.20, ge=0, le=1)


class PricingConfig(_Section):
    file: str = ""


class DashboardConfig(_Section):
    enabled: bool = True


class LicenseConfig(_Section):
    path: str = ""


class UpdateConfig(_Section):
    enabled: bool = True
    manifest_url: str = (
        "https://github.com/ahmed-dev25/ctxproxy/releases/latest/download/manifest.json"
    )
    public_key: str = ""


def _default_upstreams() -> dict[str, str | UpstreamEntry]:
    return {
        "anthropic": "https://api.anthropic.com",
        "openai": "https://api.openai.com",
        "gemini": "https://generativelanguage.googleapis.com",
        "ollama": "http://127.0.0.1:11434",
    }


class Config(_Section):
    """Effective configuration for one process."""

    schema_version: int = 1
    server: ServerConfig = Field(default_factory=ServerConfig)
    mode: ModeSettings = Field(default_factory=ModeSettings)
    upstreams: dict[str, str | UpstreamEntry] = Field(default_factory=_default_upstreams)
    http: HttpConfig = Field(default_factory=HttpConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    transforms: TransformsConfig = Field(default_factory=TransformsConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)
    waste: WasteConfig = Field(default_factory=WasteConfig)
    guard: GuardConfig = Field(default_factory=GuardConfig)
    pricing: PricingConfig = Field(default_factory=PricingConfig)
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)
    license: LicenseConfig = Field(default_factory=LicenseConfig)
    update: UpdateConfig = Field(default_factory=UpdateConfig)

    @field_validator("upstreams")
    @classmethod
    def _check_upstreams(
        cls, value: dict[str, str | UpstreamEntry]
    ) -> dict[str, str | UpstreamEntry]:
        for name, entry in value.items():
            url = entry if isinstance(entry, str) else entry.url
            if not url.startswith(("http://", "https://")):
                raise ValueError(f"upstream {name!r} url must start with http:// or https://")
        return value

    @model_validator(mode="after")
    def _check_consistency(self) -> Config:
        truncate = self.transforms.smart_truncate
        if truncate.target_bytes * 1.5 > truncate.trigger_bytes:
            raise ValueError(
                "transforms.smart_truncate.target_bytes * 1.5 must be <= trigger_bytes"
            )
        if self.transforms.cache_serve.enabled and self.telemetry.capture_payloads == "off":
            raise ValueError(
                "transforms.cache_serve.enabled requires telemetry.capture_payloads != 'off'"
            )
        return self

    @property
    def config_hash(self) -> str:
        """Hash of the settings that change forwarded bytes (SPEC section 7.1)."""
        return compute_config_hash(self)


def compute_config_hash(config: Config) -> str:
    """Return a stable sha256 over transform-effective configuration."""
    payload = {
        "transforms": config.transforms.model_dump(mode="json"),
        "tools": config.tools.model_dump(mode="json"),
        "pipeline": config.pipeline.model_dump(mode="json"),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(canonical.encode("utf-8")).hexdigest()


def default_config_path() -> Path:
    """Return the per-user config file path."""
    return Path(platformdirs.user_config_dir("ctxproxy")) / "config.toml"


def data_dir(env: Mapping[str, str] | None = None) -> Path:
    """Return the data directory, honouring ``CTXPROXY_DATA_DIR``."""
    source = os.environ if env is None else env
    override = source.get("CTXPROXY_DATA_DIR")
    if override:
        return Path(override).expanduser()
    return Path(platformdirs.user_data_dir("ctxproxy"))


def resolve_config_path(path: Path | None = None, env: Mapping[str, str] | None = None) -> Path:
    """Resolve the config path from an explicit value, env or platform default."""
    source = os.environ if env is None else env
    if path is not None:
        return path.expanduser()
    from_env = source.get("CTXPROXY_CONFIG")
    if from_env:
        return Path(from_env).expanduser()
    return default_config_path()


def default_config_text() -> str:
    """Return the commented default config shipped with the package."""
    resource = resources.files("ctxproxy").joinpath("data", CONFIG_RESOURCE)
    return resource.read_text(encoding="utf-8")


def ensure_config_file(path: Path) -> bool:
    """Create *path* from the shipped template if missing. Return True if created."""
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(default_config_text(), encoding="utf-8")
    return True


def load_config(
    *,
    path: Path | None = None,
    overrides: Mapping[str, object] | None = None,
    env: Mapping[str, str] | None = None,
) -> Config:
    """Load and validate configuration (CLI > env > file > defaults)."""
    source = dict(os.environ if env is None else env)
    explicit = path is not None or "CTXPROXY_CONFIG" in source
    config_path = resolve_config_path(path, source)
    raw: dict[str, Any] = {}
    if config_path.exists():
        with config_path.open("rb") as handle:
            raw = tomllib.load(handle)
    elif explicit:
        raise FileNotFoundError(f"config file not found: {config_path}")
    _apply_env(raw, source)
    if overrides:
        for dotted, value in overrides.items():
            _set_dotted(raw, dotted, value)
    unknown = unknown_keys(raw)
    if unknown:
        logger.warning("unknown config keys ignored: %s", ", ".join(unknown))
    return Config.model_validate(raw)


def unknown_keys(raw: Mapping[str, Any]) -> list[str]:
    """Return dotted paths present in *raw* that the config models do not define."""
    return _unknown_in(raw, Config, "")


def _unknown_in(raw: Mapping[str, Any], model: type[BaseModel], prefix: str) -> list[str]:
    found: list[str] = []
    fields = model.model_fields
    for key, value in raw.items():
        path = f"{prefix}{key}"
        field = fields.get(key)
        if field is None:
            found.append(path)
            continue
        annotation = field.annotation
        if (
            isinstance(value, Mapping)
            and isinstance(annotation, type)
            and issubclass(annotation, BaseModel)
        ):
            found.extend(_unknown_in(value, annotation, f"{path}."))
    return found


def _apply_env(raw: dict[str, Any], env: Mapping[str, str]) -> None:
    for name, dotted in _ENV_FIELDS.items():
        if name in env:
            _set_dotted(raw, dotted, env[name])
    for name, value in env.items():
        if not name.startswith(f"{ENV_PREFIX}UPSTREAM_"):
            continue
        upstream = name.removeprefix(f"{ENV_PREFIX}UPSTREAM_").lower()
        if upstream:
            _set_dotted(raw, f"upstreams.{upstream}", value)


def _set_dotted(raw: dict[str, Any], dotted: str, value: object) -> None:
    parts = dotted.split(".")
    cursor = raw
    for part in parts[:-1]:
        existing = cursor.get(part)
        if not isinstance(existing, dict):
            existing = {}
            cursor[part] = existing
        cursor = existing
    cursor[parts[-1]] = value


__all__ = [
    "CachePolicy",
    "Config",
    "CostSource",
    "Mode",
    "ShellKind",
    "UpstreamKind",
    "UsageStyle",
    "compute_config_hash",
    "data_dir",
    "default_config_path",
    "default_config_text",
    "ensure_config_file",
    "load_config",
    "resolve_config_path",
    "unknown_keys",
]
