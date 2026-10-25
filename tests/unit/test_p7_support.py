"""Break-even estimator and service plans (P6-4/P7)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ctxoptimizer.analysis.break_even import estimate_stale_elision
from ctxoptimizer.service import install_service, service_plan, uninstall_service


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
    assert mac.path.name == "com.ctxoptimizer.plist"
    assert "launchctl" in mac.commands[0]

    linux = service_plan(platform="linux", home=tmp_path, config_path="cfg.toml")
    assert linux.path.name == "ctxoptimizer.service"
    assert "ExecStart=" in linux.content
    assert "cfg.toml" in linux.content
    assert "systemctl" in linux.commands[0]


def test_service_dry_run_does_not_write(tmp_path: Path) -> None:
    plan = install_service(platform="linux", home=tmp_path, dry_run=True)
    assert not plan.path.exists()
    removed = uninstall_service(platform="linux", home=tmp_path, dry_run=True)
    assert removed.path == plan.path


def test_service_install_writes_and_runs(monkeypatch, tmp_path: Path) -> None:
    calls = []
    monkeypatch.setattr(
        "ctxoptimizer.service.subprocess.run",
        lambda command, check: calls.append(command),
    )
    plan = install_service(platform="linux", home=tmp_path, dry_run=False)
    assert plan.path.exists()
    assert calls
    uninstall_service(platform="linux", home=tmp_path, dry_run=False)
    assert not plan.path.exists()


def test_service_default_platform(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("ctxoptimizer.service.os.name", "nt")
    assert service_plan(home=tmp_path).platform == "windows"
    monkeypatch.setattr("ctxoptimizer.service.os.name", "posix")
    monkeypatch.setattr("ctxoptimizer.service.sys.platform", "darwin")
    assert service_plan(home=tmp_path).platform == "darwin"
    monkeypatch.setattr("ctxoptimizer.service.sys.platform", "linux")
    assert service_plan(home=tmp_path).platform == "linux"
