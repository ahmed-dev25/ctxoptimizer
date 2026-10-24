"""Break-even estimator, service plans and license status (P6-4/P7)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ctxproxy.analysis.break_even import estimate_stale_elision
from ctxproxy.licensing import (
    install_license,
    license_status,
    set_license_path,
    verify_license_file,
)
from ctxproxy.service import install_service, service_plan, uninstall_service


def test_break_even_estimator_is_labelled_and_conservative() -> None:
    estimate = estimate_stale_elision(
        elided_tokens=8192,
        batch_turns=8,
        input_per_mtok=3.0,
        cache_read_per_mtok=0.3,
        cache_write_per_mtok=0.0,
    )
    assert estimate.savings_per_request_usd == pytest.approx(8192 * 3.0 / 1_000_000)
    assert estimate.boundary_miss_cost_usd == pytest.approx(8192 * 2.7 / 1_000_000)
    assert estimate.requests_to_recover == pytest.approx(0.9)
    assert estimate.break_even_within_batch is True
    assert estimate.method.startswith("sim.")


def test_break_even_without_savings_is_not_claimed() -> None:
    estimate = estimate_stale_elision(
        elided_tokens=1000,
        batch_turns=8,
        input_per_mtok=0.0,
        cache_read_per_mtok=0.0,
    )
    assert estimate.savings_per_request_usd == 0.0
    assert estimate.requests_to_recover is None
    assert estimate.break_even_within_batch is False


def test_service_plan_shapes(tmp_path: Path) -> None:
    windows = service_plan(platform="windows", home=tmp_path)
    assert windows.platform == "windows"
    assert "schtasks" in windows.commands[0]
    assert "ONLOGON" in windows.commands[0]

    mac = service_plan(platform="darwin", home=tmp_path)
    assert mac.path.name == "com.ctxproxy.plist"
    assert "launchctl" in mac.commands[0]

    linux = service_plan(platform="linux", home=tmp_path, config_path="cfg.toml")
    assert linux.path.name == "ctxproxy.service"
    assert "ExecStart=" in linux.content
    assert "cfg.toml" in linux.content
    assert "systemctl" in linux.commands[0]


def test_service_dry_run_does_not_write(tmp_path: Path) -> None:
    plan = install_service(platform="linux", home=tmp_path, dry_run=True)
    assert not plan.path.exists()
    removed = uninstall_service(platform="linux", home=tmp_path, dry_run=True)
    assert removed.path == plan.path


def test_license_status_default_and_invalid(tmp_path: Path) -> None:
    set_license_path(tmp_path / "license.json")
    status = license_status()
    assert status.tier == "unlicensed"
    assert status.valid is False
    assert status.enforcement == "off"

    invalid = tmp_path / "bad.json"
    invalid.write_text("{not json", encoding="utf-8")
    assert verify_license_file(invalid).valid is False

    with pytest.raises(ValueError):
        install_license(invalid)
