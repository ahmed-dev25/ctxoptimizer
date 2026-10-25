"""Smoke tests: package wiring and CLI entry point."""

from __future__ import annotations

import importlib
import pkgutil
from importlib.util import find_spec

from typer.testing import CliRunner

import ctxoptimizer
from ctxoptimizer import __version__
from ctxoptimizer.cli import app


def test_version_is_declared() -> None:
    assert __version__ == "0.4.1"


def test_cli_reports_version() -> None:
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_license_command_is_removed() -> None:
    result = CliRunner().invoke(app, ["license"])
    assert result.exit_code != 0


def test_config_has_no_license_section() -> None:
    from ctxoptimizer.config import Config

    assert "license" not in Config.model_fields
    assert find_spec("ctxoptimizer.licensing") is None


def test_update_command_is_removed() -> None:
    result = CliRunner().invoke(app, ["update"])
    assert result.exit_code != 0


def test_config_has_no_update_section() -> None:
    from ctxoptimizer.config import Config

    assert "update" not in Config.model_fields
    assert find_spec("ctxoptimizer.update") is None


def test_every_module_imports() -> None:
    modules = list(pkgutil.walk_packages(ctxoptimizer.__path__, prefix="ctxoptimizer."))
    assert modules, "expected submodules to exist"
    for info in modules:
        importlib.import_module(info.name)
