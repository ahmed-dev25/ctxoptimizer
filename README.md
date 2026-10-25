# ctxproxy

A local, deterministic cost optimizer for AI coding agents. It sits between your
agent and the LLM provider, measures real token usage and spend, explains why
prompt caching missed, and applies cache-safe payload reductions.

- **Local only** — binds to loopback; no telemetry leaves the machine.
- **Deterministic** — no LLM calls inside the proxy; every decision is a hash,
  regex, counter or threshold.
- **Honest numbers** — provider-reported usage is ground truth; everything else
  is labelled `est.` or `sim.`.
- **Fail-open** — invalid transforms retry with the original bytes; the proxy
  never blocks traffic.

## Install

```powershell
uv tool install ctxproxy
# or: pipx install ctxproxy
ctxproxy run
```

From a checkout:

```powershell
uv sync --extra dev
uv run ctxproxy run
```

The startup banner prints the dashboard URL with a per-run admin token:

```text
dashboard: http://127.0.0.1:8787/_ctxproxy/?token=...
```

Open that URL once; the token is stored as an `HttpOnly; SameSite=Strict`
cookie. The dashboard is also protected by a Host allowlist and CSRF checks.

## Quickstart

```powershell
ctxproxy env --shell powershell   # bash | zsh | fish | powershell
ctxproxy status                   # health + counters
ctxproxy stats                    # recorded usage and cost
```

Point a client at the printed base URL. See
[`docs/client-setup.md`](docs/client-setup.md) for Claude Code, OpenCode,
DeepSeek, OpenRouter, Gemini, Ollama, Codex and the other supported clients.

Default mode is `shadow`: everything is measured and simulated, while the
client's bytes are forwarded unchanged. Switch to `active` from the dashboard
(Settings), with `ctxproxy run --mode active`, or with
`x-ctxproxy-mode: active` per request.

## What it does

- Measures provider usage and cost for Anthropic, OpenAI Chat/Responses,
  native Gemini, native Ollama and named OpenAI-compatible upstreams
  (DeepSeek, OpenRouter, Gemini/Ollama compatibility, and custom gateways).
- Detects drift (tools/system/history/TTL/config/model) and waste W1–W8:
  redundant re-reads, identical outputs, unbatched fan-out, runaway sessions,
  recurring/param drift, edit churn and unused tool schemas.
- Applies deterministic transforms: ANSI/progress cleanup, line dedupe,
  whitespace trim, signal-aware truncation, duplicate back-references,
  byte-true `cache_serve`, opt-in stale-result elision, Anthropic
  `cache_control` hints and OpenAI `prompt_cache_key`.
- Auto-quarantines a transform per session when fallback/drift guard counters
  trip; the dashboard shows the history and lets you re-enable it.
- Provides `ctxproxy_expand` over MCP so an agent can retrieve any omitted
  original from the local blob store.
- Serves a local dashboard: Overview, Live (SSE), Sessions, Requests + diff
  viewer, Waste Opportunities with status controls, Transforms with hot
  toggles/stats, Pricing editor, Settings and Doctor.

## Privacy

Payload capture defaults to `changed_blocks`; set it to `off` to store nothing.
Captured text stays in the per-user data directory, is redacted, and is bounded
by retention. `ctxproxy purge --all` wipes telemetry, blobs and findings. See
[`docs/privacy.md`](docs/privacy.md).

## Service

```powershell
ctxproxy service install        # launchd / systemd --user / Windows scheduled task
ctxproxy service install --dry-run
```

## License

ctxproxy is free and open-source software licensed under the **MIT License**.
See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).

## Updating

Use the package manager that installed ctxproxy:

```powershell
uv tool upgrade ctxproxy
# or
pipx upgrade ctxproxy
```

There is no built-in self-update command. Release integrity is provided by the
package index/GitHub release channel and TLS. See
[`docs/updating.md`](docs/updating.md).

## Documentation

- [`SPEC.md`](SPEC.md) — authoritative specification
- [`docs/client-setup.md`](docs/client-setup.md) — per-client recipes
- [`docs/how-to-use.md`](docs/how-to-use.md) — complete install/run/update guide
- [`docs/provider-notes.md`](docs/provider-notes.md) — dated provider behavior
- [`docs/architecture.md`](docs/architecture.md) — component overview
- [`docs/privacy.md`](docs/privacy.md) — data handling and purge
- [`docs/faq.md`](docs/faq.md) — cache, savings, troubleshooting
- [`docs/test-report.md`](docs/test-report.md) — gates and test coverage summary
- [`docs/updating.md`](docs/updating.md) — package-manager upgrades and release artifacts
- [`docs/release-checklist.md`](docs/release-checklist.md) — release/signing checklist
- [`docs/progress.md`](docs/progress.md) — build status and handoff notes
- [`CHANGELOG.md`](CHANGELOG.md)
- [`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md)
- [`docs/decisions/`](docs/decisions/) — architecture decision records
- [`AGENTS.md`](AGENTS.md) — coding and git workflow rules

## Development

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy --strict src
uv run pytest -q
uv build --wheel
```

Supported Python: 3.11+. The package is built with `uv_build`; the test suite
uses a real fake upstream and recorded/documented fixtures. Live provider tests
are opt-in (`pytest -m live`) and require keys.
