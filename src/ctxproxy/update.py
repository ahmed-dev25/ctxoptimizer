"""Signed self-update support (P10).

The update manifest is a small JSON document:

    {"version":"0.3.1","url":"https://.../ctxproxy-0.3.1.whl",
     "sha256":"...","signature":"base64 Ed25519"}

Signatures cover the canonical JSON of every field except ``signature``.
Artifacts are checked against both the signature and SHA-256 before install.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import url2pathname

import httpx

from ctxproxy import __version__
from ctxproxy.config import Config


class UpdateError(RuntimeError):
    """Raised when an update cannot be verified or applied."""


@dataclass(frozen=True, slots=True)
class UpdateManifest:
    version: str
    url: str
    sha256: str
    signature: str | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateCheck:
    current: str
    latest: str
    available: bool
    manifest: UpdateManifest


def parse_manifest(
    payload: dict[str, Any],
    *,
    public_key: str | None,
    allow_unsigned: bool = False,
) -> UpdateManifest:
    version = payload.get("version")
    url = payload.get("url")
    digest = payload.get("sha256")
    signature = payload.get("signature")
    if not (isinstance(version, str) and version):
        raise UpdateError("manifest requires a version")
    if not (isinstance(url, str) and url):
        raise UpdateError("manifest requires a url")
    if not (isinstance(digest, str) and digest):
        raise UpdateError("manifest requires a sha256")
    if len(digest) != 64:
        raise UpdateError("sha256 must be 64 hex characters")
    if not allow_unsigned:
        if not signature:
            raise UpdateError("manifest is unsigned")
        if not public_key:
            raise UpdateError("no update public key configured")
        _verify_signature(payload, signature, public_key)
    return UpdateManifest(
        version=str(version),
        url=str(url),
        sha256=str(digest).lower(),
        signature=str(signature) if signature else None,
        notes=payload.get("notes") if isinstance(payload.get("notes"), str) else None,
    )


def _verify_signature(payload: dict[str, Any], signature: str, public_key: str) -> None:
    try:
        from nacl.exceptions import BadSignatureError
        from nacl.signing import VerifyKey
    except ImportError as exc:
        raise UpdateError("install the [license] extra to verify updates") from exc
    message = {key: value for key, value in payload.items() if key != "signature"}
    canonical = json.dumps(message, sort_keys=True, separators=(",", ":")).encode()
    try:
        raw_key = base64.b64decode(public_key)
        VerifyKey(raw_key).verify(canonical, base64.b64decode(signature))
    except (ValueError, BadSignatureError) as exc:
        raise UpdateError("bad update signature") from exc


def fetch_manifest(
    url: str, *, public_key: str | None, allow_unsigned: bool = False
) -> UpdateManifest:
    parsed = urlparse(url)
    if parsed.scheme == "file":
        try:
            payload = json.loads(Path(url2pathname(parsed.path)).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise UpdateError(f"cannot read manifest: {exc}") from exc
    elif parsed.scheme == "https":
        try:
            response = httpx.get(url, timeout=10.0, follow_redirects=True)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise UpdateError(f"cannot fetch manifest: {exc}") from exc
    else:
        raise UpdateError("manifest URL must be https (or file:// for local testing)")
    if not isinstance(payload, dict):
        raise UpdateError("manifest must be a JSON object")
    return parse_manifest(payload, public_key=public_key, allow_unsigned=allow_unsigned)


def check_update(config: Config) -> UpdateCheck:
    manifest = fetch_manifest(
        config.update.manifest_url, public_key=config.update.public_key or None
    )
    return UpdateCheck(
        current=__version__,
        latest=manifest.version,
        available=version_tuple(manifest.version) > version_tuple(__version__),
        manifest=manifest,
    )


def version_tuple(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for chunk in value.replace("v", "").split(".")[:4]:
        digits = ""
        for char in chunk:
            if char.isdigit():
                digits += char
            else:
                break
        parts.append(int(digits or 0))
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts)


def download_artifact(manifest: UpdateManifest, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / Path(urlparse(manifest.url).path).name
    if not target.name:
        target = directory / "ctxproxy-update"
    parsed = urlparse(manifest.url)
    if parsed.scheme == "file":
        try:
            shutil.copyfile(url2pathname(parsed.path), target)
        except OSError as exc:
            raise UpdateError(f"copy failed: {exc}") from exc
    else:
        try:
            with httpx.stream("GET", manifest.url, timeout=60.0, follow_redirects=True) as response:
                response.raise_for_status()
                with target.open("wb") as handle:
                    for chunk in response.iter_bytes():
                        handle.write(chunk)
        except (httpx.HTTPError, OSError) as exc:
            target.unlink(missing_ok=True)
            raise UpdateError(f"download failed: {exc}") from exc
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if digest != manifest.sha256:
        target.unlink(missing_ok=True)
        raise UpdateError("artifact SHA-256 mismatch")
    return target


def install_artifact(path: Path, *, dry_run: bool = False) -> str:
    if path.suffix.lower() == ".whl":
        command = [sys.executable, "-m", "pip", "install", "--upgrade", str(path)]
        if dry_run:
            return "would run: " + " ".join(command)
        result = subprocess.run(command, check=False)  # noqa: S603
        if result.returncode != 0:
            raise UpdateError("pip install failed; update the wheel manually")
        return "wheel installed"

    if not getattr(sys, "frozen", False):
        return (
            "artifact downloaded and verified; binary replacement is only "
            "automatic for the frozen build"
        )
    executable = Path(sys.executable)
    if dry_run:
        return f"would replace {executable}"
    backup = executable.with_name(executable.name + ".old")
    try:
        if backup.exists():
            backup.unlink()
        if os.name == "nt":
            executable.rename(backup)
            shutil.move(str(path), str(executable))
        else:
            shutil.copy2(executable, backup)
            os.replace(path, executable)
    except OSError as exc:
        raise UpdateError(f"binary replacement failed: {exc}") from exc
    return f"replaced {executable}; restart ctxproxy"


def perform_update(
    config: Config,
    *,
    check_only: bool = False,
    allow_unsigned: bool = False,
    dry_run: bool = False,
) -> UpdateCheck:
    manifest = fetch_manifest(
        config.update.manifest_url,
        public_key=config.update.public_key or None,
        allow_unsigned=allow_unsigned,
    )
    current = __version__
    available = version_tuple(manifest.version) > version_tuple(current)
    result = UpdateCheck(current, manifest.version, available, manifest)
    if check_only or not available:
        return result
    with tempfile.TemporaryDirectory(prefix="ctxproxy-update-") as temp:
        artifact = download_artifact(manifest, Path(temp))
        install_artifact(artifact, dry_run=dry_run)
    return result


__all__ = [
    "UpdateCheck",
    "UpdateError",
    "UpdateManifest",
    "check_update",
    "download_artifact",
    "fetch_manifest",
    "install_artifact",
    "parse_manifest",
    "perform_update",
    "version_tuple",
]
