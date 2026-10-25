"""Smoke tests: package wiring, CLI entry point and license stub."""

from __future__ import annotations

import importlib
import pkgutil

from typer.testing import CliRunner

import ctxproxy
from ctxproxy import __version__
from ctxproxy.cli import app
from ctxproxy.licensing import is_active_mode_allowed, license_status


def test_version_is_declared() -> None:
    assert __version__ == "0.3.0"


def test_cli_reports_version() -> None:
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_license_stub_allows_active_mode() -> None:
    assert is_active_mode_allowed() is True
    status = license_status()
    assert status.enforcement == "off"
    assert status.valid is False


def test_every_module_imports() -> None:
    modules = list(pkgutil.walk_packages(ctxproxy.__path__, prefix="ctxproxy."))
    assert modules, "expected submodules to exist"
    for info in modules:
        importlib.import_module(info.name)
