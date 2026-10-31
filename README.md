# ctxoptimizer

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
uv tool install ctxoptimizer
# or: pipx install ctxoptimizer
ctxoptimizer run
```

If PyPI does not have the release yet, install from GitHub:

```powershell
uv tool install "git+https://github.com/ahmed-dev25/ctxoptimizer.git"
# or: pipx install "git+https://github.com/ahmed-dev25/ctxoptimizer.git"
ctxoptimizer run
```

From a checkout:

```powershell
uv sync --extra dev
uv run ctxoptimizer run
```

The startup banner prints the dashboard URL with a per-run admin token:

```text
dashboard: http://127.0.0.1:8787/_ctxoptimizer/?token=...
```

Open that URL once; the token is stored as an `HttpOnly; SameSite=Strict`
cookie. The dashboard is also protected by a Host allowlist and CSRF checks.

## Quickstart

```powershell
ctxoptimizer env --shell powershell   # bash | zsh | fish | powershell
ctxoptimizer status                   # health + counters
ctxoptimizer stats                    # recorded usage and cost
```

Point a client at the printed base URL. See
[`docs/client-setup.md`](docs/client-setup.md) for Claude Code, OpenCode,
DeepSeek, OpenRouter, Gemini, Ollama, Codex and the other supported clients.

### Use in another repo

Start the proxy once (or install it at login):

```powershell
ctxoptimizer run
# or
ctxoptimizer service install
```

Then set the base URL in that repo's shell, `.env`, or client config. The
`/p/<project>` segment is optional and keeps stats separated per repository.

```dotenv
# .env — only works if your client actually loads .env files
ANTHROPIC_BASE_URL=http://127.0.0.1:8787/p/my-project
OPENAI_BASE_URL=http://127.0.0.1:8787/p/my-project/v1
```

PowerShell equivalent:

```powershell
$env:ANTHROPIC_BASE_URL = "http://127.0.0.1:8787/p/my-project"
$env:OPENAI_BASE_URL = "http://127.0.0.1:8787/p/my-project/v1"
```

For OpenCode, add the provider to that repo's `opencode.json` with
`options.baseURL` set to
`http://127.0.0.1:8787/p/my-project/u/deepseek`. Do not commit `.env` files or
provider API keys.

Check the repo's usage with:

```powershell
ctxoptimizer stats --project my-project
```

Default mode is `shadow`: everything is measured and simulated, while the
client's bytes are forwarded unchanged. Switch to `active` from the dashboard
(Settings), with `ctxoptimizer run --mode active`, or with
`x-ctxoptimizer-mode: active` per request.

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
- Provides `ctxoptimizer_expand` over MCP so an agent can retrieve any omitted
  original from the local blob store.
- Serves a local dashboard: Overview, Live (SSE), Sessions, Requests + diff
  viewer, Waste Opportunities with status controls, Transforms with hot
  toggles/stats, Pricing editor, Settings and Doctor.

## Privacy

Payload capture defaults to `changed_blocks`; set it to `off` to store nothing.
Captured text stays in the per-user data directory, is redacted, and is bounded
by retention. `ctxoptimizer purge --all` wipes telemetry, blobs and findings. See
[`docs/privacy.md`](docs/privacy.md).

## Service

```powershell
ctxoptimizer service install        # launchd / systemd --user / Windows scheduled task
ctxoptimizer service install --dry-run
```

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for development setup and gates. Report
vulnerabilities privately via [`SECURITY.md`](SECURITY.md); do not open a public
issue for a security problem.

## License

ctxoptimizer is free and open-source software licensed under the **MIT License**.
See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).

## Updating

Use the package manager that installed ctxoptimizer:

```powershell
uv tool upgrade ctxoptimizer
# or
pipx upgrade ctxoptimizer
```

There is no built-in self-update command. PyPI releases are published with
Trusted Publishing and PEP 740 attestations. Source installs follow the GitHub
repository; downloaded wheels must be replaced manually. See
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
- [`docs/pypi-release.md`](docs/pypi-release.md) — PyPI Trusted Publishing setup
- [`docs/release-checklist.md`](docs/release-checklist.md) — release checklist
- [`docs/progress.md`](docs/progress.md) — build status and handoff notes
- [`CHANGELOG.md`](CHANGELOG.md)
- [`CONTRIBUTING.md`](CONTRIBUTING.md)
- [`SECURITY.md`](SECURITY.md)
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
