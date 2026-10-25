"""License checks (SPEC section 19).

Offline Ed25519 verification. Enforcement is a build flag and stays ``off`` in
this open build (ADR 0002); the module still reports the status of a supplied
license so a paid build can flip one constant.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

LICENSE_ENFORCEMENT: Literal["on", "off"] = "off"

# Paid builds replace this with their base64 Ed25519 public key. Never put the
# private key in the repository.
_EMBEDDED_PUBLIC_KEY = ""
_PUBLIC_KEY_ENV = "CTXPROXY_LICENSE_PUBLIC_KEY"

_license_path: Path | None = None


@dataclass(frozen=True, slots=True)
class LicenseStatus:
    """Result of a license check."""

    tier: str
    valid: bool
    enforcement: Literal["on", "off"]
    reason: str
    email: str | None = None
    expires_at: str | None = None
    features: tuple[str, ...] = ()


def set_license_path(path: Path | str | None) -> None:
    global _license_path
    _license_path = Path(path).expanduser() if path else None


def default_license_path() -> Path:
    from ctxproxy.config import data_dir

    return data_dir() / "license.json"


def install_license(source: Path | str) -> Path:
    """Copy a license file to the private data dir (0600 on POSIX)."""
    src = Path(source).expanduser()
    status = verify_license_file(src)
    if not status.valid:
        raise ValueError(status.reason)
    destination = default_license_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, destination)
    if os.name == "posix":
        os.chmod(destination, 0o600)
    set_license_path(destination)
    return destination


def is_active_mode_allowed() -> bool:
    if LICENSE_ENFORCEMENT == "off":
        return True
    return license_status().valid


def license_status(path: Path | str | None = None) -> LicenseStatus:
    target = Path(path).expanduser() if path else (_license_path or default_license_path())
    if not target.exists():
        return LicenseStatus(
            tier="unlicensed",
            valid=False,
            enforcement=LICENSE_ENFORCEMENT,
            reason=f"no license file at {target}"
            if LICENSE_ENFORCEMENT == "on"
            else "license enforcement disabled in this build",
        )
    return verify_license_file(target)


def verify_license_file(path: Path | str) -> LicenseStatus:
    target = Path(path).expanduser()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _invalid(f"cannot read license: {exc}")
    if not isinstance(payload, dict):
        return _invalid("license must be a JSON object")
    signature = payload.get("sig")
    if not isinstance(signature, str):
        return _invalid("license is unsigned")
    public_key = _public_key()
    if not public_key:
        return _invalid("no license public key configured in this build")
    message = {key: value for key, value in payload.items() if key != "sig"}
    canonical = json.dumps(message, sort_keys=True, separators=(",", ":")).encode("utf-8")
    try:
        from nacl.exceptions import BadSignatureError
        from nacl.signing import VerifyKey

        VerifyKey(public_key).verify(canonical, base64.b64decode(signature))
    except ImportError:
        return _invalid("license extra is not installed (uv sync --extra license)")
    except (BadSignatureError, ValueError):
        return _invalid("bad license signature")

    expires = payload.get("expires_at")
    if expires is not None:
        expiry = _parse_time(expires)
        if expiry is None:
            return _invalid("unparseable expires_at")
        if expiry < time.time():
            return LicenseStatus(
                tier=str(payload.get("tier") or "unknown"),
                valid=False,
                enforcement=LICENSE_ENFORCEMENT,
                reason="license expired",
                email=_str_or_none(payload.get("email")),
                expires_at=str(expires),
                features=_features(payload.get("features")),
            )
    return LicenseStatus(
        tier=str(payload.get("tier") or "unknown"),
        valid=True,
        enforcement=LICENSE_ENFORCEMENT,
        reason="valid offline license",
        email=_str_or_none(payload.get("email")),
        expires_at=str(expires) if expires else None,
        features=_features(payload.get("features")),
    )


def _public_key() -> bytes | None:
    value = os.environ.get(_PUBLIC_KEY_ENV) or _EMBEDDED_PUBLIC_KEY
    if not value:
        return None
    try:
        raw = base64.b64decode(value)
    except ValueError:
        return None
    return raw if len(raw) == 32 else None


def _invalid(reason: str) -> LicenseStatus:
    return LicenseStatus(
        tier="unlicensed",
        valid=False,
        enforcement=LICENSE_ENFORCEMENT,
        reason=reason,
    )


def _parse_time(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.timestamp()


def _str_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _features(value: Any) -> tuple[str, ...]:
    return tuple(str(item) for item in value) if isinstance(value, list) else ()


__all__ = [
    "LICENSE_ENFORCEMENT",
    "LicenseStatus",
    "default_license_path",
    "install_license",
    "is_active_mode_allowed",
    "license_status",
    "set_license_path",
    "verify_license_file",
]
