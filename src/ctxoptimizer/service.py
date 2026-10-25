"""Autostart service generation (SPEC section 21, P7-1).

Generates a per-user launchd/systemd/scheduled-task registration. The pure
``service_plan`` helper is testable without touching the host.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ServicePlan:
    platform: str
    path: Path
    content: str
    commands: tuple[tuple[str, ...], ...]
    remove_commands: tuple[tuple[str, ...], ...]


def service_plan(
    *, platform: str | None = None, home: Path | None = None, config_path: str | None = None
) -> ServicePlan:
    name = platform or _platform()
    home = home or Path.home()
    args = [sys.executable, "-m", "ctxoptimizer", "run"]
    if config_path:
        args.extend(["--config", config_path])
    command = " ".join(_quote(part) for part in args)

    if name == "windows":
        task = "ctxoptimizer"
        return ServicePlan(
            platform=name,
            path=home / "AppData" / "Local" / "ctxoptimizer" / "ctxoptimizer-service.txt",
            content=f"Scheduled task {task}: {command}\n",
            commands=(
                (
                    "schtasks",
                    "/Create",
                    "/SC",
                    "ONLOGON",
                    "/TN",
                    task,
                    "/TR",
                    command,
                    "/F",
                ),
            ),
            remove_commands=(("schtasks", "/Delete", "/TN", task, "/F"),),
        )

    if name == "darwin":
        plist = home / "Library" / "LaunchAgents" / "com.ctxoptimizer.plist"
        content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.ctxoptimizer</string>
  <key>ProgramArguments</key><array>
    {"".join(f"<string>{_xml(part)}</string>" for part in args)}
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
</dict></plist>
"""
        return ServicePlan(
            platform=name,
            path=plist,
            content=content,
            commands=(("launchctl", "load", str(plist)),),
            remove_commands=(("launchctl", "unload", str(plist)),),
        )

    unit = home / ".config" / "systemd" / "user" / "ctxoptimizer.service"
    content = (
        "[Unit]\n"
        "Description=ctxoptimizer local LLM proxy\n"
        "After=network-online.target\n\n"
        "[Service]\n"
        "Type=simple\n"
        f"ExecStart={command}\n"
        "Restart=on-failure\n\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )
    return ServicePlan(
        platform="linux",
        path=unit,
        content=content,
        commands=(
            ("systemctl", "--user", "daemon-reload"),
            ("systemctl", "--user", "enable", "--now", "ctxoptimizer.service"),
        ),
        remove_commands=(("systemctl", "--user", "disable", "--now", "ctxoptimizer.service"),),
    )


def install_service(
    *,
    platform: str | None = None,
    home: Path | None = None,
    config_path: str | None = None,
    dry_run: bool = False,
) -> ServicePlan:
    plan = service_plan(platform=platform, home=home, config_path=config_path)
    if dry_run:
        return plan
    plan.path.parent.mkdir(parents=True, exist_ok=True)
    plan.path.write_text(plan.content, encoding="utf-8")
    for command in plan.commands:
        subprocess.run(command, check=False)  # noqa: S603
    return plan


def uninstall_service(
    *,
    platform: str | None = None,
    home: Path | None = None,
    dry_run: bool = False,
) -> ServicePlan:
    plan = service_plan(platform=platform, home=home)
    if dry_run:
        return plan
    for command in plan.remove_commands:
        subprocess.run(command, check=False)  # noqa: S603
    plan.path.unlink(missing_ok=True)
    return plan


def _platform() -> str:
    if os.name == "nt":
        return "windows"
    if sys.platform == "darwin":
        return "darwin"
    return "linux"


def _quote(value: str) -> str:
    return f'"{value}"' if " " in value else value


def _xml(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


__all__ = ["ServicePlan", "install_service", "service_plan", "uninstall_service"]
