"""Admin service helpers: validated config patches, pricing writes, exports."""

from __future__ import annotations

import csv
import io
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from starlette.applications import Starlette

from ctxproxy.config import Config, data_dir, load_config
from ctxproxy.models import WasteFinding
from ctxproxy.telemetry.pricing import load_pricing


def deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in patch.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = deep_merge(current, value)
        else:
            merged[key] = value
    return merged


def apply_config_patch(app: Starlette, patch: dict[str, Any]) -> Config:
    """Validate a partial config update and make it live in this process."""
    current = app.state.config
    merged = deep_merge(current.model_dump(mode="json"), patch)
    updated = Config.model_validate(merged)
    _install(app, updated)
    return updated


def reload_config(app: Starlette) -> Config:
    path = getattr(app.state, "config_path", None)
    updated = load_config(path=Path(path) if path else None)
    _install(app, updated)
    return updated


def _install(app: Starlette, updated: Config) -> None:
    app.state.config = updated
    guard = getattr(app.state, "guard", None)
    if guard is not None:
        guard.config = updated


def config_view(config: Config) -> dict[str, Any]:
    data = config.model_dump(mode="json")
    server = data.get("server")
    if isinstance(server, dict):
        server["admin_token"] = "***" if server.get("admin_token") else ""
    return data


def parse_since(value: str | None) -> float | None:
    if not value:
        return None
    now = time.time()
    for suffix, seconds in (("m", 60), ("h", 3600), ("d", 86_400)):
        if value.endswith(suffix) and value[:-1].isdigit():
            return now - int(value[:-1]) * seconds
    try:
        return float(value)
    except ValueError:
        return None


def rows_to_csv(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def write_pricing(config: Config, payload: dict[str, Any]) -> tuple[Config, Path]:
    """Validate and persist a pricing override, then return the new config."""
    models = payload.get("models")
    if not isinstance(models, list):
        raise ValueError("pricing payload must contain a models list")
    path = Path(config.pricing.file) if config.pricing.file else data_dir() / "pricing.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"models": models}, indent=2) + "\n", encoding="utf-8")
    try:
        table = load_pricing(path)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    if not table.models:
        raise ValueError("pricing file has no valid models")
    updated = config.model_copy(
        update={"pricing": config.pricing.model_copy(update={"file": str(path)})}
    )
    return updated, path


def findings_from_rows(rows: list[dict[str, Any]]) -> list[WasteFinding]:
    findings: list[WasteFinding] = []
    for row in rows:
        try:
            evidence = json.loads(str(row.get("evidence_json") or "{}"))
        except json.JSONDecodeError:
            evidence = {}
        findings.append(
            WasteFinding(
                finding_id=str(row.get("finding_id")),
                ts=float(row.get("ts") or 0.0),
                session_id=str(row.get("session_id") or ""),
                project=row.get("project"),
                detector=str(row.get("detector") or "unknown"),
                key_hash=bytes.fromhex(str(row.get("key_hash") or "")),
                request_id=row.get("request_id"),
                occurrences=int(row.get("occurrences") or 1),
                first_seen_ts=float(row.get("first_seen_ts") or 0.0),
                last_seen_ts=float(row.get("last_seen_ts") or 0.0),
                evidence=evidence,
                est_tokens_wasted=row.get("est_tokens_wasted"),
                est_cost_usd=row.get("est_cost_usd"),
                status=row.get("status") or "new",
            )
        )
    return findings


def pricing_payload(config: Config) -> dict[str, Any]:
    try:
        table = load_pricing(Path(config.pricing.file) if config.pricing.file else None)
    except (OSError, ValueError, KeyError):
        table = load_pricing(None)
    return {
        "version": table.version,
        "currency": table.currency,
        "per": table.per,
        "models": [asdict(model) for model in table.models],
    }


__all__ = [
    "apply_config_patch",
    "config_view",
    "deep_merge",
    "findings_from_rows",
    "parse_since",
    "pricing_payload",
    "reload_config",
    "rows_to_csv",
    "write_pricing",
]
