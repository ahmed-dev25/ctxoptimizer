# ctxproxy

A local, deterministic cost optimizer for AI coding agents. It sits between your
agent and the LLM provider, measures real token usage and spend, explains why
prompt caching missed, and applies cache-safe payload reductions.

- **Local only** — binds to loopback; no telemetry leaves the machine.
- **Deterministic** — no LLM calls inside the proxy; every decision is a hash,
  regex, counter or threshold.
- **Honest numbers** — provider-reported usage is ground truth; everything else
  is labelled `est.` or `sim.`.

## Status

P1 alpha. The proxy, ground-truth telemetry, pricing, SQLite store and CLI are
working. Transforms, drift detection, waste attribution and the dashboard land in
later phases. The default operating mode is `shadow`: observe and report, forward
the request untouched.

## Quickstart

```powershell
uv run ctxproxy run
uv run ctxproxy env --shell powershell
uv run ctxproxy status
uv run ctxproxy stats
```

Point a client at the printed base URL. See
[`docs/client-setup.md`](docs/client-setup.md) for Claude Code, OpenCode,
DeepSeek, OpenRouter, Codex and the other supported clients.

## Documentation

- [`SPEC.md`](SPEC.md) — authoritative specification (v2.0)
- [`docs/architecture.html`](docs/architecture.html) — visual architecture reference
- [`docs/plan.md`](docs/plan.md) — current milestone plan
- [`docs/progress.md`](docs/progress.md) — build status and handoff notes
- [`docs/decisions/`](docs/decisions/) — architecture decision records
- [`AGENTS.md`](AGENTS.md) — coding and git workflow rules
