"""Shared diagnostic checks for the CLI and dashboard Doctor page (P5)."""

from __future__ import annotations

import importlib.util
import socket
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ctxoptimizer.config import LOOPBACK_HOSTS, Config, data_dir
from ctxoptimizer.telemetry.pricing import load_pricing


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    ok: bool
    detail: str
    warning: bool = False


def run_checks(config: Config, *, offline: bool = True) -> list[Check]:
    checks: list[Check] = []
    checks.append(
        Check(
            "bind host",
            config.server.host in LOOPBACK_HOSTS or config.server.allow_remote,
            config.server.host,
        )
    )
    db_path = (
        Path(config.telemetry.db_path)
        if config.telemetry.db_path
        else data_dir() / "ctxoptimizer.db"
    )
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute("PRAGMA user_version").fetchone()
        checks.append(Check("database writable", True, str(db_path)))
    except Exception as exc:
        checks.append(Check("database writable", False, str(exc)))

    try:
        table = load_pricing(Path(config.pricing.file) if config.pricing.file else None)
        verified = sum(1 for price in table.models if price.verified)
        checks.append(
            Check(
                "pricing",
                True,
                f"version {table.version}, {verified} verified entries",
            )
        )
        try:
            age = (date.today() - date.fromisoformat(table.version)).days
            if age > 60:
                checks.append(
                    Check(
                        "pricing age",
                        False,
                        f"{age} days; check provider pages",
                        warning=True,
                    )
                )
        except ValueError:
            checks.append(
                Check(
                    "pricing age",
                    False,
                    f"unparseable version {table.version!r}",
                    warning=True,
                )
            )
    except Exception as exc:
        checks.append(Check("pricing", False, str(exc)))

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((config.server.host, config.server.port))
        checks.append(Check("port free", True, str(config.server.port)))
    except OSError:
        checks.append(
            Check(
                "port free",
                False,
                f"{config.server.port} already in use (is ctxoptimizer running?)",
                warning=True,
            )
        )

    checks.append(
        Check(
            "tiktoken",
            importlib.util.find_spec("tiktoken") is not None,
            "available" if importlib.util.find_spec("tiktoken") else "fallback estimator",
            warning=True,
        )
    )
    if config.transforms.cache_serve.enabled and config.telemetry.capture_payloads == "off":
        checks.append(
            Check(
                "cache_serve capture",
                False,
                "cache_serve requires capture_payloads != off",
            )
        )
    if not offline:
        import httpx

        for name, entry in sorted(config.upstreams.items()):
            base = entry if isinstance(entry, str) else entry.url
            try:
                response = httpx.head(base, timeout=2.0, follow_redirects=False)
                checks.append(
                    Check(
                        f"upstream {name}",
                        response.status_code < 500,
                        f"HTTP {response.status_code}",
                        warning=True,
                    )
                )
            except httpx.HTTPError as exc:
                checks.append(Check(f"upstream {name}", False, str(exc), warning=True))

    return checks


__all__ = ["Check", "run_checks"]
