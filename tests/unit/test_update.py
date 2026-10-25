"""Signed update manifest and download verification."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ctxproxy.config import Config
from ctxproxy.update import (
    UpdateError,
    check_update,
    download_artifact,
    fetch_manifest,
    install_artifact,
    parse_manifest,
    perform_update,
    version_tuple,
)


def _manifest(url: str, digest: str, version: str = "9.9.9") -> dict:
    return {"version": version, "url": url, "sha256": digest}


def test_manifest_requires_signature_by_default() -> None:
    with pytest.raises(UpdateError, match="unsigned"):
        parse_manifest(_manifest("https://example.com/a.whl", "a" * 64), public_key=None)


def test_manifest_validation_and_versions() -> None:
    manifest = parse_manifest(
        _manifest("https://example.com/a.whl", "a" * 64),
        public_key=None,
        allow_unsigned=True,
    )
    assert manifest.version == "9.9.9"
    assert version_tuple("0.10.2") > version_tuple("0.9.9")
    assert version_tuple("v1.2.3") == (1, 2, 3, 0)


def test_download_verifies_sha256(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.whl"
    artifact.write_bytes(b"wheel")
    digest = hashlib.sha256(b"wheel").hexdigest()
    manifest = parse_manifest(
        _manifest(artifact.as_uri(), digest), public_key=None, allow_unsigned=True
    )
    downloaded = download_artifact(manifest, tmp_path / "download")
    assert downloaded.read_bytes() == b"wheel"

    bad = parse_manifest(
        _manifest(artifact.as_uri(), "b" * 64), public_key=None, allow_unsigned=True
    )
    with pytest.raises(UpdateError, match="SHA-256"):
        download_artifact(bad, tmp_path / "bad")


def test_check_update_from_file_manifest(tmp_path: Path) -> None:
    artifact = tmp_path / "ctxproxy-9.9.9.whl"
    artifact.write_bytes(b"wheel")
    manifest = _manifest(artifact.as_uri(), hashlib.sha256(b"wheel").hexdigest())
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    fetched = fetch_manifest(path.as_uri(), public_key=None, allow_unsigned=True)
    assert fetched.version == "9.9.9"

    config = Config.model_validate({"update": {"manifest_url": path.as_uri()}})
    result = perform_update(config, check_only=True, allow_unsigned=True)
    assert result.available is True
    assert result.current != result.latest


def test_install_artifact_dry_run_for_wheel(tmp_path: Path) -> None:
    wheel = tmp_path / "x.whl"
    wheel.write_bytes(b"")
    assert "would run" in install_artifact(wheel, dry_run=True)


def test_cli_update_check(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from ctxproxy.cli import app

    artifact = tmp_path / "ctxproxy-9.9.9.whl"
    artifact.write_bytes(b"wheel")
    manifest = _manifest(artifact.as_uri(), hashlib.sha256(b"wheel").hexdigest())
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    result = CliRunner().invoke(
        app,
        ["update", "--check", "--manifest", path.as_uri(), "--allow-unsigned"],
    )
    assert result.exit_code == 0
    assert "9.9.9" in result.stdout
    assert "update available" in result.stdout


def test_manifest_field_and_transport_errors(tmp_path: Path) -> None:
    for payload in (
        {},
        {"version": "1", "url": "https://x", "sha256": "short"},
        {"version": "1", "url": "https://x"},
    ):
        with pytest.raises(UpdateError):
            parse_manifest(payload, public_key=None, allow_unsigned=True)
    with pytest.raises(UpdateError, match="https"):
        fetch_manifest("http://example.com/manifest.json", public_key=None)
    with pytest.raises(UpdateError, match="cannot read"):
        fetch_manifest((tmp_path / "missing.json").as_uri(), public_key=None)


def test_signature_requires_update_extra() -> None:
    payload = {
        "version": "1.0.0",
        "url": "https://example.com/x.whl",
        "sha256": "a" * 64,
        "signature": "not-a-real-signature",
    }
    with pytest.raises(UpdateError):
        parse_manifest(payload, public_key="abcd")


def test_perform_update_downloads_and_installs_dry_run(tmp_path: Path) -> None:
    artifact = tmp_path / "ctxproxy-9.9.9.whl"
    artifact.write_bytes(b"wheel")
    manifest = _manifest(artifact.as_uri(), hashlib.sha256(b"wheel").hexdigest())
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    config = Config.model_validate({"update": {"manifest_url": path.as_uri()}})
    result = perform_update(config, allow_unsigned=True, dry_run=True)
    assert result.available is True
    assert install_artifact(artifact, dry_run=True).startswith("would run")


def test_check_update_uses_fetch(monkeypatch) -> None:
    config = Config.model_validate({"update": {"manifest_url": "https://example.com/m.json"}})
    manifest = parse_manifest(
        _manifest("https://example.com/x.whl", "a" * 64),
        public_key=None,
        allow_unsigned=True,
    )
    monkeypatch.setattr("ctxproxy.update.fetch_manifest", lambda *args, **kwargs: manifest)
    result = check_update(config)
    assert result.latest == "9.9.9"
    assert result.available is True


def test_binary_install_paths(monkeypatch, tmp_path: Path) -> None:
    artifact = tmp_path / "ctxproxy"
    artifact.write_bytes(b"binary")
    message = install_artifact(artifact, dry_run=False)
    assert "binary replacement" in message
    monkeypatch.setattr("sys.frozen", True, raising=False)
    assert "would replace" in install_artifact(artifact, dry_run=True)


def test_fetch_https_manifest(monkeypatch) -> None:
    payload = _manifest("https://example.com/x.whl", "a" * 64)

    class Response:
        def raise_for_status(self) -> None:
            return

        def json(self) -> dict:
            return payload

    monkeypatch.setattr("ctxproxy.update.httpx.get", lambda *args, **kwargs: Response())
    manifest = fetch_manifest(
        "https://example.com/manifest.json", public_key=None, allow_unsigned=True
    )
    assert manifest.version == "9.9.9"


def test_frozen_binary_replacement(monkeypatch, tmp_path: Path) -> None:
    from types import SimpleNamespace

    executable = tmp_path / "ctxproxy.exe"
    executable.write_bytes(b"old")
    artifact = tmp_path / "new-binary"
    artifact.write_bytes(b"new")
    monkeypatch.setattr(
        "ctxproxy.update.sys",
        SimpleNamespace(executable=str(executable), frozen=True),
    )
    message = install_artifact(artifact, dry_run=False)
    assert "replaced" in message
    assert executable.read_bytes() == b"new"
    assert (tmp_path / "ctxproxy.exe.old").exists()


def test_frozen_binary_replacement_posix(monkeypatch, tmp_path: Path) -> None:
    import os
    from types import SimpleNamespace

    executable = tmp_path / "ctxproxy"
    executable.write_bytes(b"old")
    artifact = tmp_path / "new-binary"
    artifact.write_bytes(b"new")
    monkeypatch.setattr(
        "ctxproxy.update.sys",
        SimpleNamespace(executable=str(executable), frozen=True),
    )
    monkeypatch.setattr(
        "ctxproxy.update.os",
        SimpleNamespace(name="posix", replace=os.replace),
    )
    install_artifact(artifact, dry_run=False)
    assert executable.read_bytes() == b"new"
    assert (tmp_path / "ctxproxy.old").read_bytes() == b"old"


def test_wheel_install_runs_pip(monkeypatch, tmp_path: Path) -> None:
    import subprocess

    wheel = tmp_path / "x.whl"
    wheel.write_bytes(b"")
    calls = []
    monkeypatch.setattr(
        "ctxproxy.update.subprocess.run",
        lambda command, check: calls.append(command) or subprocess.CompletedProcess(command, 0),
    )
    assert install_artifact(wheel, dry_run=False) == "wheel installed"
    assert calls and calls[0][:3] == [__import__("sys").executable, "-m", "pip"]


def test_signed_manifest_roundtrip() -> None:
    pytest.importorskip("nacl.signing")
    import base64

    from nacl.signing import SigningKey

    key = SigningKey.generate()
    payload = _manifest("https://example.com/x.whl", "a" * 64)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    payload["signature"] = base64.b64encode(key.sign(canonical).signature).decode()
    public = base64.b64encode(bytes(key.verify_key)).decode()
    manifest = parse_manifest(payload, public_key=public)
    assert manifest.version == "9.9.9"
    payload["sha256"] = "b" * 64
    with pytest.raises(UpdateError, match="signature"):
        parse_manifest(payload, public_key=public)
