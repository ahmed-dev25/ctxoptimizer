"""Smoke tests: package wiring and CLI entry point."""

from __future__ import annotations

import importlib
import pkgutil
from importlib.util import find_spec

from typer.testing import CliRunner

import ctxproxy
from ctxproxy import __version__
from ctxproxy.cli import app


def test_version_is_declared() -> None:
    assert __version__ == "0.4.0"


def test_cli_reports_version() -> None:
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_license_command_is_removed() -> None:
    result = CliRunner().invoke(app, ["license"])
    assert result.exit_code != 0


def test_config_has_no_license_section() -> None:
    from ctxproxy.config import Config

    assert "license" not in Config.model_fields
    assert find_spec("ctxproxy.licensing") is None


def test_every_module_imports() -> None:
    modules = list(pkgutil.walk_packages(ctxproxy.__path__, prefix="ctxproxy."))
    assert modules, "expected submodules to exist"
    for info in modules:
        importlib.import_module(info.name)
