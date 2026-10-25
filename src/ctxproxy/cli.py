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
from ctxproxy.admin_security import load_tokens, save_tokens
from ctxproxy.analysis.recommend import recommendations
from ctxproxy.config import (
    LOOPBACK_HOSTS,
    Config,
    data_dir,
    default_config_path,
    ensure_config_file,
    load_config,
)
from ctxproxy.dashboard.service import findings_from_rows
from ctxproxy.models import Endpoint, Mode, Provider, RequestContext
from ctxproxy.pipeline import run_pipeline
from ctxproxy.providers import adapter_for
from ctxproxy.server import create_app
from ctxproxy.service import install_service, uninstall_service
from ctxproxy.telemetry.blobs import BlobStore
from ctxproxy.telemetry.pricing import load_pricing
from ctxproxy.telemetry.redact import redact_text
from ctxproxy.telemetry.store import default_db_path
from ctxproxy.transforms import build_transforms
from ctxproxy.update import UpdateError, perform_update

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
    if config_path is None:
        ensure_config_file(default_config_path())
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
    if config.server.allow_remote:
        typer.echo("warning: remote admin access is enabled; keep the token private")
    app = create_app(config, config_path=config_path)
    save_tokens(app.state.admin_token, app.state.csrf_token)
    typer.echo(
        "dashboard: "
        f"http://{config.server.host}:{config.server.port}/_ctxproxy/"
        f"?token={app.state.admin_token}"
    )
    uvicorn.run(
        app,
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
def mode(
    value: Annotated[str, typer.Argument(help="passthrough | shadow | active")],
    config_path: Annotated[Path | None, typer.Option("--config")] = None,
) -> None:
    """Switch mode at runtime via the admin API."""
    if value not in {"passthrough", "shadow", "active"}:
        raise typer.BadParameter("mode must be passthrough, shadow or active")
    config = _load(config_path)
    try:
        data = _admin_request(config, "POST", "/_ctxproxy/api/mode", {"mode": value})
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"mode: {data.get('mode')}")


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
    since: Annotated[str | None, typer.Option("--since")] = None,
    project: Annotated[str | None, typer.Option("--project")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Print a terminal summary of recorded requests and cost."""
    config = _load(config_path)
    rows = _read_rows(_db_path(config), _parse_since(since), 100_000)
    if project:
        rows = [row for row in rows if row.get("project") == project]
    requests = len(rows)
    cost = sum(float(row.get("cost_actual_usd") or 0.0) for row in rows)
    baseline = sum(float(row.get("cost_baseline_sim_usd") or 0.0) for row in rows)
    fresh = sum(int(row.get("fresh_input") or 0) for row in rows)
    read = sum(int(row.get("cache_read") or 0) for row in rows)
    output = sum(int(row.get("output_tokens") or 0) for row in rows)
    ratio = (read / (read + fresh)) if (read + fresh) else 0.0
    data = {
        "requests": requests,
        "actual_cost_usd": cost,
        "baseline_sim_usd": baseline,
        "savings_sim_usd": max(baseline - cost, 0.0),
        "fresh_input": fresh,
        "cache_read": read,
        "cache_hit_ratio": ratio,
        "output_tokens": output,
    }
    if json_output:
        typer.echo(json.dumps(data, indent=2))
        return
    typer.echo(f"requests: {requests}")
    typer.echo(f"actual cost: ${cost:.6f}")
    typer.echo(f"baseline cost (sim.): ${baseline:.6f}")
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
        reports = _read_reports(_db_path(config), _parse_since(since), limit)
        text = json.dumps({"requests": rows, "transform_reports": reports}, indent=2, default=str)
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


guard_app = typer.Typer(help="Inspect or override per-session transform quarantine.")
app.add_typer(guard_app, name="guard")


@guard_app.command("status")
def guard_show(
    config_path: Annotated[Path | None, typer.Option("--config")] = None,
) -> None:
    """Show quarantined transforms."""
    config = _load(config_path)
    try:
        data = _admin_request(config, "GET", "/_ctxproxy/api/guard")
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    for item in data.get("quarantined", []):
        typer.echo(f"{item['transform_id']}\t{item['session_id']}\t{item['reason']}")


def _guard_action(
    action: str,
    transform: str,
    session: str | None,
    config_path: Path | None,
) -> None:
    config = _load(config_path)
    body = {"action": action, "transform_id": transform}
    if session:
        body["session_id"] = session
    try:
        data = _admin_request(config, "POST", "/_ctxproxy/api/guard", body)
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"{action}: {data.get('transform_id')} ({len(data.get('sessions', []))} session(s))")


@guard_app.command("enable")
def guard_enable(
    transform: Annotated[str, typer.Argument()],
    session: Annotated[str | None, typer.Option("--session")] = None,
    config_path: Annotated[Path | None, typer.Option("--config")] = None,
) -> None:
    """Re-enable a transform (optionally for one session)."""
    _guard_action("enable", transform, session, config_path)


@guard_app.command("disable")
def guard_disable(
    transform: Annotated[str, typer.Argument()],
    session: Annotated[str | None, typer.Option("--session")] = None,
    config_path: Annotated[Path | None, typer.Option("--config")] = None,
) -> None:
    """Quarantine a transform (optionally for one session)."""
    _guard_action("disable", transform, session, config_path)


@app.command()
def waste(
    config_path: Annotated[Path | None, typer.Option("--config")] = None,
    project: Annotated[str | None, typer.Option("--project")] = None,
    since: Annotated[str | None, typer.Option("--since")] = None,
    detector: Annotated[str | None, typer.Option("--detector")] = None,
    summary: Annotated[bool, typer.Option("--summary")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List open waste findings ranked by estimated cost."""
    config = _load(config_path)
    rows = _read_findings(_db_path(config), _parse_since(since))
    if project:
        rows = [row for row in rows if row.get("project") == project]
    if detector:
        rows = [row for row in rows if row.get("detector") == detector]
    if summary:
        rollup: dict[str, dict[str, float]] = {}
        for row in rows:
            item = rollup.setdefault(
                str(row.get("detector")), {"findings": 0, "tokens": 0.0, "cost": 0.0}
            )
            item["findings"] += 1
            item["tokens"] += float(row.get("est_tokens_wasted") or 0)
            item["cost"] += float(row.get("est_cost_usd") or 0)
        if json_output:
            typer.echo(json.dumps(rollup, indent=2))
            return
        for name, item in sorted(rollup.items(), key=lambda pair: -pair[1]["cost"]):
            typer.echo(
                f"{name}\tfindings={int(item['findings'])} "
                f"est_tokens={int(item['tokens'])} est_usd={item['cost']:.6f}"
            )
        return
    if json_output:
        typer.echo(json.dumps(rows, indent=2))
        return
    for row in rows:
        typer.echo(
            f"{row.get('detector')}\t{row.get('session_id')}\t"
            f"est_tokens={row.get('est_tokens_wasted')}\t"
            f"est_usd={row.get('est_cost_usd')}\tstatus={row.get('status')}"
        )


@app.command()
def recommend(
    config_path: Annotated[Path | None, typer.Option("--config")] = None,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Print ranked recommendations with evidence."""
    config = _load(config_path)
    findings = findings_from_rows(_read_findings(_db_path(config), None))
    items = recommendations(
        findings,
        cache_serve_enabled=config.transforms.cache_serve.enabled,
        volatile_normalizer_enabled=config.transforms.volatile_normalizer.enabled,
        transforms_enabled=True,
    )
    if json_output:
        typer.echo(json.dumps(items, indent=2))
        return
    for item in items:
        typer.echo(f"{item['title']} [{item['label']}]")
        typer.echo(f"  {item['evidence']}")
        typer.echo(f"  action: {item['action']}")


@app.command()
def replay(
    path: Annotated[Path, typer.Argument(help="captured request JSON")],
    provider: Annotated[str, typer.Option("--provider")] = "anthropic",
    endpoint: Annotated[str, typer.Option("--endpoint")] = "messages",
    mode: Annotated[str, typer.Option("--mode")] = "active",
    config_path: Annotated[Path | None, typer.Option("--config")] = None,
) -> None:
    """Run the pipeline on one request offline; print reports and changed blocks."""
    config = _load(config_path, {"mode.default": mode} if mode else None)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        provider_enum = Provider(provider)
        endpoint_enum = Endpoint(endpoint)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if not isinstance(payload, dict):
        typer.echo("error: request JSON must be an object", err=True)
        raise typer.Exit(code=1)
    adapter = adapter_for(provider_enum, endpoint_enum)
    ctx = RequestContext(
        request_id="replay",
        provider=provider_enum,
        endpoint=endpoint_enum,
        upstream_name=provider_enum.value,
        model=adapter.model_of(payload),
        stream=adapter.is_stream(payload),
        mode=Mode(mode),
        session_id="replay",
        project=None,
        client_name="replay",
        config=config,
        config_hash=config.config_hash,
        started_monotonic=time.monotonic(),
    )
    result = run_pipeline(ctx, payload, adapter, build_transforms(config), config)
    for report in result.reports:
        typer.echo(
            f"{report.transform_id}\tchanged={report.changed}\t"
            f"tokens={report.est_tokens_before}->{report.est_tokens_after}\t"
            f"{report.discarded_reason or ''}"
        )
    typer.echo(f"total: {result.orig_est_tokens} -> {result.final_est_tokens} est. tokens")
    for index, (before, after) in enumerate(result.changed_blocks, start=1):
        typer.echo(f"--- block {index} before ---")
        typer.echo(before)
        typer.echo(f"--- block {index} after ---")
        typer.echo(after)


@app.command()
def bench(
    rounds: Annotated[int, typer.Option("--rounds")] = 25,
) -> None:
    """Run a small synthetic pipeline benchmark."""
    config = _load(None, {"mode.default": "active"})
    adapter = adapter_for(Provider.ANTHROPIC, Endpoint.MESSAGES)
    samples: list[float] = []
    for _ in range(max(1, rounds)):
        messages: list[dict[str, Any]] = [{"role": "user", "content": "bench"}]
        for index in range(20):
            messages.extend(
                [
                    {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": f"t{index}",
                                "name": "Bash",
                                "input": {"command": "pytest -q"},
                            }
                        ],
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": f"t{index}",
                                "content": "\x1b[31mFAILED\x1b[0m\n" * 200,
                            }
                        ],
                    },
                ]
            )
        payload = {"model": "claude-sonnet-4-5", "messages": messages}
        ctx = RequestContext(
            request_id="bench",
            provider=Provider.ANTHROPIC,
            endpoint=Endpoint.MESSAGES,
            upstream_name="anthropic",
            model="claude-sonnet-4-5",
            stream=False,
            mode=Mode.ACTIVE,
            session_id="bench",
            project=None,
            client_name="bench",
            config=config,
            config_hash=config.config_hash,
            started_monotonic=time.monotonic(),
        )
        started = time.perf_counter()
        run_pipeline(ctx, payload, adapter, build_transforms(config), config)
        samples.append((time.perf_counter() - started) * 1000)
    samples.sort()
    p50 = samples[len(samples) // 2]
    p95 = samples[max(0, int(len(samples) * 0.95) - 1)]
    typer.echo(f"rounds={len(samples)} p50_ms={p50:.2f} p95_ms={p95:.2f}")


@app.command()
def capture(
    out: Annotated[Path, typer.Option("--out")],
    request_id: Annotated[str | None, typer.Option("--request")] = None,
    sanitize: Annotated[bool, typer.Option("--sanitize")] = False,
    config_path: Annotated[Path | None, typer.Option("--config")] = None,
) -> None:
    """Export stored request metadata and changed blocks as review fixtures."""
    config = _load(config_path)
    db_path = _db_path(config)
    rows = _read_rows(db_path, None, 1000)
    if request_id:
        rows = [row for row in rows if row["request_id"] == request_id]
    blobs = BlobStore(data_dir() / "blobs")
    written = 0
    for row in rows:
        target = out / str(row["request_id"])
        target.mkdir(parents=True, exist_ok=True)
        meta = {key: value for key, value in row.items() if not key.startswith("_")}
        (target / "meta.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
        blocks = _capture_blocks(db_path, str(row["request_id"]), blobs, sanitize)
        (target / "blocks.json").write_text(json.dumps(blocks, indent=2), encoding="utf-8")
        for block in blocks:
            location = block.get("location")
            text = block.get("before") or ""
            if location == "request":
                (target / "request.json").write_text(text, encoding="utf-8")
            elif location == "final_request":
                (target / "request.final.json").write_text(text, encoding="utf-8")
            elif location == "response":
                suffix = "sse" if _looks_sse(text) else "json"
                (target / f"response.{suffix}").write_text(text, encoding="utf-8")
        written += 1
    typer.echo(f"wrote {written} fixture(s) to {out}")


@app.command()
def update(
    config_path: Annotated[Path | None, typer.Option("--config")] = None,
    manifest: Annotated[str | None, typer.Option("--manifest")] = None,
    public_key: Annotated[str | None, typer.Option("--public-key")] = None,
    check_only: Annotated[bool, typer.Option("--check")] = False,
    allow_unsigned: Annotated[bool, typer.Option("--allow-unsigned")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y")] = False,
) -> None:
    """Check for or install a signed ctxproxy update."""
    overrides: dict[str, object] = {}
    if manifest:
        overrides["update.manifest_url"] = manifest
    if public_key:
        overrides["update.public_key"] = public_key
    config = _load(config_path, overrides or None)
    if allow_unsigned:
        typer.echo("warning: unsigned update explicitly allowed", err=True)
    try:
        if check_only:
            result = perform_update(config, check_only=True, allow_unsigned=allow_unsigned)
            typer.echo(f"current: {result.current}")
            typer.echo(f"latest:  {result.latest}")
            typer.echo("update available" if result.available else "up to date")
            return
        if not yes:
            typer.confirm("Install the latest verified update?", abort=True)
        result = perform_update(config, allow_unsigned=allow_unsigned, dry_run=dry_run)
    except UpdateError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"current: {result.current}")
    typer.echo(f"latest:  {result.latest}")
    typer.echo("up to date" if not result.available else "update verified and installed")


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


def _capture_blocks(
    db_path: Path, request_id: str, blobs: BlobStore, sanitize: bool
) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM captures WHERE request_id = ? ORDER BY rowid",
            (request_id,),
        ).fetchall()
    blocks: list[dict[str, Any]] = []
    for row in rows:
        before = blobs.get(row["before_hash"] or "")
        after = blobs.get(row["after_hash"] or "")
        blocks.append(
            {
                "location": row["location"],
                "before": _fixture_text(before, sanitize),
                "after": _fixture_text(after, sanitize),
            }
        )
    return blocks


def _fixture_text(data: bytes | None, sanitize: bool) -> str | None:
    if data is None:
        return None
    text = redact_text(data.decode("utf-8", "replace"))
    if sanitize:
        import re

        text = re.sub(r"[A-Za-z]:\\Users\\[^\\\s]+", "<home>", text)
        text = re.sub(r"/(?:home|Users)/[^/\s]+", "<home>", text)
        text = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "user@example.com", text)
    return text


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


def _looks_sse(text: str) -> bool:
    return "data:" in text and "\n\n" in text


def _read_reports(db_path: Path, since_ts: float | None, limit: int) -> list[_Request]:
    if not db_path.exists():
        return []
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        query = (
            "SELECT transform_reports.*, requests.ts FROM transform_reports "
            "JOIN requests USING(request_id)"
        )
        params: list[Any] = []
        if since_ts is not None:
            query += " WHERE requests.ts >= ?"
            params.append(since_ts)
        query += " ORDER BY requests.ts DESC LIMIT ?"
        params.append(limit)
        return [dict(row) for row in conn.execute(query, params).fetchall()]


def _read_findings(db_path: Path, since_ts: float | None) -> list[_Request]:
    if not db_path.exists():
        return []
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        query = "SELECT * FROM waste_findings WHERE status IN ('new', 'ack')"
        params: list[Any] = []
        if since_ts is not None:
            query += " AND first_seen_ts >= ?"
            params.append(since_ts)
        query += " ORDER BY est_cost_usd DESC, ts DESC"
        return [dict(row) for row in conn.execute(query, params).fetchall()]


def _admin_request(
    config: Config,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    admin_token, csrf_token = load_tokens()
    admin_token = admin_token or config.server.admin_token
    if not admin_token:
        raise RuntimeError("no admin token found; start `ctxproxy run` first")
    headers = {"x-ctxproxy-admin-token": admin_token}
    if method.upper() not in {"GET", "HEAD", "OPTIONS"}:
        if not csrf_token:
            raise RuntimeError("no CSRF token found; start `ctxproxy run` first")
        headers["x-ctxproxy-csrf"] = csrf_token
    base = f"http://{config.server.host}:{config.server.port}"
    response = httpx.request(
        method,
        f"{base}{path}",
        json=body,
        headers=headers,
        timeout=5.0,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text}")
    data = response.json()
    return data if isinstance(data, dict) else {"data": data}


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

service_app = typer.Typer(help="Install or remove the per-user autostart service.")
app.add_typer(service_app, name="service")


@service_app.command("install")
def service_install(
    config_path: Annotated[Path | None, typer.Option("--config")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Install launchd/systemd/scheduled-task autostart."""
    plan = install_service(config_path=str(config_path) if config_path else None, dry_run=dry_run)
    typer.echo(f"platform: {plan.platform}")
    typer.echo(f"unit: {plan.path}")
    for command in plan.commands:
        typer.echo("run: " + " ".join(command))
    if dry_run:
        typer.echo("(dry run; nothing written or executed)")


@service_app.command("uninstall")
def service_uninstall(
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Remove the autostart service."""
    plan = uninstall_service(dry_run=dry_run)
    for command in plan.remove_commands:
        typer.echo("run: " + " ".join(command))
    typer.echo(f"removed: {plan.path}")


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
