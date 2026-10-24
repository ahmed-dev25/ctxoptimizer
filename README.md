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

Pre-alpha. P0 (scaffolding) and P1 (transparent proxy + ground-truth telemetry)
are in progress. Nothing is shipped yet. The default operating mode is `shadow`:
observe and report, forward the request untouched.

## Documentation

- [`SPEC.md`](SPEC.md) — authoritative specification (v2.0)
- [`docs/architecture.html`](docs/architecture.html) — visual architecture reference
- [`docs/plan.md`](docs/plan.md) — current milestone plan
- [`docs/progress.md`](docs/progress.md) — build status and handoff notes
- [`docs/decisions/`](docs/decisions/) — architecture decision records
- [`AGENTS.md`](AGENTS.md) — coding and git workflow rules

## Quickstart

Not available yet. The quickstart lands at the end of Phase 1.
