"""Command line interface (SPEC section 15).

P1 commands: run, status, env, doctor, stats, export, purge.
"""

from __future__ import annotations

import csv
import io
import json
import shlex
import socket
import sqlite3
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated, Any

import httpx
import typer
import uvicorn

from ctxproxy import __version__
from ctxproxy.config import LOOPBACK_HOSTS, Config, load_config
from ctxproxy.server import create_app
from ctxproxy.telemetry.pricing import load_pricing
from ctxproxy.telemetry.store import default_db_path

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Local, deterministic cost optimizer for AI coding agents.",
)

_SHELLS = ("bash", "zsh", "fish", "powershell")
_Request = dict[str, Any]


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit(code=0)


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            is_eager=True,
            callback=_version_callback,
            help="Show the ctxproxy version and exit.",
        ),
    ] = False,
) -> None:
    """ctxproxy command line."""


@app.command()
def run(
    host: Annotated[str | None, typer.Option("--host")] = None,
    port: Annotated[int | None, typer.Option("--port")] = None,
    mode: Annotated[str | None, typer.Option("--mode")] = None,
    config_path: Annotated[Path | None, typer.Option("--config")] = None,
) -> None:
    """Start the proxy in the foreground."""
    overrides: dict[str, object] = {}
    if host:
        overrides["server.host"] = host
    if port:
        overrides["server.port"] = port
    if mode:
        overrides["mode.default"] = mode
    config = _load(config_path, overrides or None)
    typer.echo(
        f"ctxproxy {__version__} listening on "
        f"http://{config.server.host}:{config.server.port} ({config.mode.default})"
    )
    uvicorn.run(
        create_app(config),
        host=config.server.host,
        port=config.server.port,
        log_level=config.server.log_level,
        access_log=False,
    )


@app.command()
def status(
    url: Annotated[str | None, typer.Option("--url")] = None,
    config_path: Annotated[Path | None, typer.Option("--config")] = None,
) -> None:
    """Query a running proxy's health endpoint."""
    config = _load(config_path)
    target = url or f"http://{config.server.host}:{config.server.port}"
    try:
        response = httpx.get(f"{target}/_ctxproxy/health", timeout=2.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        typer.echo(f"error: cannot reach {target}: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    data = response.json()
    for key in (
        "status",
        "version",
        "mode",
        "uptime_s",
        "requests",
        "completed",
        "client_disconnect",
        "upstream_errors",
        "dropped_telemetry",
        "stored_requests",
        "last_model",
        "last_cost_usd",
        "last_usage_source",
    ):
        typer.echo(f"{key}: {data.get(key)}")


@app.command()
def env(
    shell: Annotated[str, typer.Option("--shell")] = "bash",
    host: Annotated[str | None, typer.Option("--host")] = None,
    port: Annotated[int | None, typer.Option("--port")] = None,
    config_path: Annotated[Path | None, typer.Option("--config")] = None,
) -> None:
    """Print client base-URL exports for the current shell."""
    if shell not in _SHELLS:
        raise typer.BadParameter(f"shell must be one of {', '.join(_SHELLS)}")
    config = _load(config_path)
    actual_host = host or config.server.host
    actual_port = port or config.server.port
    base = f"http://{actual_host}:{actual_port}"
    values: dict[str, str] = {
        "ANTHROPIC_BASE_URL": base,
        "OPENAI_BASE_URL": f"{base}/v1",
    }
    for name in sorted(config.upstreams):
        if name in {"anthropic", "openai", "gemini", "ollama"}:
            continue
        values[f"CTXPROXY_{name.upper()}_BASE_URL"] = f"{base}/u/{name}"
    for name, value in values.items():
        typer.echo(_export_line(shell, name, value))


@app.command()
def doctor(
    config_path: Annotated[Path | None, typer.Option("--config")] = None,
    offline: Annotated[bool, typer.Option("--offline")] = False,
) -> None:
    """Check the local configuration, storage and upstream reachability."""
    config = _load(config_path)
    failures = 0

    def report(ok: bool, label: str, detail: str = "") -> None:
        nonlocal failures
        if not ok:
            failures += 1
        suffix = f": {detail}" if detail else ""
        typer.echo(f"[{'ok' if ok else 'fail'}] {label}{suffix}")

    def note(label: str, detail: str) -> None:
        typer.echo(f"[warn] {label}: {detail}")

    report(
        config.server.host in LOOPBACK_HOSTS or config.server.allow_remote,
        "bind host",
        config.server.host,
    )

    db_path = _db_path(config)
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute("PRAGMA user_version").fetchone()
        report(True, "database writable", str(db_path))
    except Exception as exc:
        report(False, "database writable", str(exc))

    try:
        table = load_pricing(Path(config.pricing.file) if config.pricing.file else None)
        verified = sum(1 for price in table.models if price.verified)
        typer.echo(f"[ok] pricing: version {table.version}, {verified} verified entries")
        try:
            age_days = (date.today() - date.fromisoformat(table.version)).days
            if age_days > 60:
                note("pricing age", f"{age_days} days; check provider pages")
        except ValueError:
            note("pricing age", f"unparseable version {table.version!r}")
    except Exception as exc:
        report(False, "pricing", str(exc))

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((config.server.host, config.server.port))
        typer.echo(f"[ok] port free: {config.server.port}")
    except OSError:
        note("port", f"{config.server.port} is already in use (is ctxproxy running?)")

    try:
        import importlib.util

        if importlib.util.find_spec("tiktoken") is not None:
            typer.echo("[ok] tiktoken available")
        else:
            note("tiktoken", "not installed; using the fallback estimator")
    except Exception as exc:
        note("tiktoken", str(exc))

    if not offline:
        for name, entry in sorted(config.upstreams.items()):
            base = entry if isinstance(entry, str) else entry.url
            try:
                response = httpx.head(base, timeout=2.0, follow_redirects=False)
                reachable = response.status_code < 500
            except httpx.HTTPError as exc:
                reachable = False
                note(f"upstream {name}", str(exc))
            else:
                typer.echo(
                    f"[{'ok' if reachable else 'warn'}] upstream {name}: "
                    f"HTTP {response.status_code}"
                )

    typer.echo("clients: claude-code, opencode, codex, aider, cline")
    typer.echo("hint: `ctxproxy env --shell powershell` prints base-URL exports")
    if failures:
        raise typer.Exit(code=1)


@app.command()
def stats(
    config_path: Annotated[Path | None, typer.Option("--config")] = None,
) -> None:
    """Print a terminal summary of recorded requests and cost."""
    config = _load(config_path)
    rows = _read_rows(_db_path(config), None, 100_000)
    requests = len(rows)
    cost = sum(float(row.get("cost_actual_usd") or 0.0) for row in rows)
    fresh = sum(int(row.get("fresh_input") or 0) for row in rows)
    read = sum(int(row.get("cache_read") or 0) for row in rows)
    output = sum(int(row.get("output_tokens") or 0) for row in rows)
    ratio = (read / (read + fresh)) if (read + fresh) else 0.0
    typer.echo(f"requests: {requests}")
    typer.echo(f"actual cost: ${cost:.6f}")
    typer.echo(f"fresh input: {fresh}")
    typer.echo(f"cache read: {read}")
    typer.echo(f"cache hit ratio: {ratio:.1%}")
    typer.echo(f"output tokens: {output}")


@app.command("export")
def export_command(
    format: Annotated[str, typer.Option("--format")] = "json",
    since: Annotated[str | None, typer.Option("--since")] = None,
    limit: Annotated[int, typer.Option("--limit")] = 1000,
    out: Annotated[Path | None, typer.Option("--out")] = None,
    config_path: Annotated[Path | None, typer.Option("--config")] = None,
) -> None:
    """Export recorded requests as JSON or CSV."""
    config = _load(config_path)
    rows = _read_rows(_db_path(config), _parse_since(since), limit)
    if format == "json":
        text = json.dumps(rows, indent=2, default=str)
    elif format == "csv":
        text = _to_csv(rows)
    else:
        raise typer.BadParameter("format must be json or csv")
    if out is None:
        typer.echo(text)
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        typer.echo(f"wrote {len(rows)} rows to {out}")


@app.command()
def purge(
    all_data: Annotated[bool, typer.Option("--all")] = False,
    days: Annotated[int, typer.Option("--days")] = 14,
    config_path: Annotated[Path | None, typer.Option("--config")] = None,
) -> None:
    """Delete recorded telemetry, either everything or rows older than N days."""
    config = _load(config_path)
    db_path = _db_path(config)
    if not db_path.exists():
        typer.echo("nothing to purge")
        return
    with sqlite3.connect(db_path) as conn:
        if all_data:
            for statement in (
                "DELETE FROM captures",
                "DELETE FROM blobs",
                "DELETE FROM guard_events",
                "DELETE FROM waste_findings",
                "DELETE FROM drift_events",
                "DELETE FROM transform_reports",
                "DELETE FROM requests",
                "DELETE FROM sessions",
            ):
                conn.execute(statement)
            conn.commit()
            typer.echo("purged all telemetry")
        else:
            cutoff = time.time() - days * 86_400
            deleted = conn.execute("DELETE FROM requests WHERE ts < ?", (cutoff,)).rowcount
            conn.commit()
            typer.echo(f"purged {deleted} request(s) older than {days} day(s)")


def _load(path: Path | None, overrides: dict[str, object] | None = None) -> Config:
    try:
        return load_config(path=path, overrides=overrides)
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def _db_path(config: Config) -> Path:
    return Path(config.telemetry.db_path) if config.telemetry.db_path else default_db_path()


def _export_line(shell: str, name: str, value: str) -> str:
    if shell == "powershell":
        return f'$env:{name} = "{value}"'
    if shell == "fish":
        return f"set -gx {name} {shlex.quote(value)}"
    return f'export {name}="{value}"'


def _parse_since(value: str | None) -> float | None:
    if not value:
        return None
    now = time.time()
    for suffix, seconds in (("m", 60), ("h", 3600), ("d", 86_400)):
        if value.endswith(suffix) and value[:-1].isdigit():
            return now - int(value[:-1]) * seconds
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter("--since must be 30m, 24h, 7d or an ISO timestamp") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.timestamp()


def _read_rows(db_path: Path, since_ts: float | None, limit: int) -> list[_Request]:
    if not db_path.exists():
        return []
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        query = "SELECT * FROM requests"
        params: list[Any] = []
        if since_ts is not None:
            query += " WHERE ts >= ?"
            params.append(since_ts)
        query += " ORDER BY ts DESC LIMIT ?"
        params.append(limit)
        return [dict(row) for row in conn.execute(query, params).fetchall()]


def _to_csv(rows: list[_Request]) -> str:
    if not rows:
        return ""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


mcp_app = typer.Typer(help="MCP integration for ctxproxy_expand.")
app.add_typer(mcp_app, name="mcp")


@mcp_app.command("run")
def mcp_run() -> None:
    """Serve the expand tool over stdio."""
    from ctxproxy.mcp import run_stdio

    run_stdio()


@mcp_app.command("snippet")
def mcp_snippet(
    client: Annotated[str, typer.Option("--client")] = "claude-code",
) -> None:
    """Print a registration snippet for an MCP client."""
    typer.echo(
        json.dumps(
            {
                "mcpServers": {"ctxproxy": {"command": "ctxproxy", "args": ["mcp", "run"]}},
                "client": client,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    app()
