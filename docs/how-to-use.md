# How to use ctxoptimizer

This is the end-to-end guide for installing, configuring and running ctxoptimizer.

## 1. What ctxoptimizer does

ctxoptimizer sits between an AI coding client and its provider:

```text
client -> http://127.0.0.1:8787 -> provider
```

It records real usage/cost, detects cache drift and waste, optionally applies
deterministic payload reductions, and serves a local dashboard.

It does **not** translate between providers. The client must already speak the
provider's protocol; only its base URL changes.

## 2. Requirements

- Windows, macOS or Linux.
- Python **3.11+**.
- An API key for the provider/client you use. ctxoptimizer forwards the client's own
  credentials and does not store them.

## 3. Install

### PyPI (recommended)

```powershell
uv tool install ctxoptimizer
# or
pipx install ctxoptimizer
```

If PyPI does not have the release yet, install from GitHub:

```powershell
uv tool install "git+https://github.com/ahmed-dev25/ctxoptimizer.git"
# or
pipx install "git+https://github.com/ahmed-dev25/ctxoptimizer.git"
```

This requires Git on `PATH`. From a local wheel:

```powershell
uv tool install --force .\ctxoptimizer-0.4.1-py3-none-any.whl
```

From a checkout:

```powershell
git clone https://github.com/ahmed-dev25/ctxoptimizer.git
cd ctxoptimizer
uv sync --extra dev
uv run ctxoptimizer --version
```

No optional signature extra is required; ctxoptimizer has no built-in self-update.

## 4. Verify the installation

```powershell
ctxoptimizer --version
# 0.4.1
```

If the command is not found on Windows:

```powershell
$env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"
ctxoptimizer --version
```

Close and reopen terminals after PATH changes. If you use Git Bash/WSL, use the
Windows executable path or add the Windows bin directory to that shell.

## 5. First run

```powershell
ctxoptimizer run
```

The banner prints:

```text
ctxoptimizer 0.4.1 listening on http://127.0.0.1:8787 (shadow)
dashboard: http://127.0.0.1:8787/_ctxoptimizer/?token=...
```

Keep this terminal open. Stop with `Ctrl+C`.

Default mode is **shadow**: ctxoptimizer measures and simulates but forwards the
client's bytes unchanged.

### Dashboard

Open the printed URL once. The token is stored as an `HttpOnly; SameSite=Strict`
cookie. The dashboard is protected by a Host allowlist, admin token and CSRF.

### Config and data locations

Windows (actual paths):

```text
Config: %LOCALAPPDATA%\ctxoptimizer\ctxoptimizer\config.toml
Data:   %LOCALAPPDATA%\ctxoptimizer\ctxoptimizer\
DB:     %LOCALAPPDATA%\ctxoptimizer\ctxoptimizer\ctxoptimizer.db
Blobs:  %LOCALAPPDATA%\ctxoptimizer\ctxoptimizer\blobs\
```

Linux/macOS:

```text
Config: ~/.config/ctxoptimizer/config.toml
Data:   ~/.local/share/ctxoptimizer/
```

`ctxoptimizer run` creates the default config on first run.

## 6. Configure upstreams

Default upstreams:

```toml
[upstreams]
anthropic = "https://api.anthropic.com"
openai = "https://api.openai.com"
gemini = "https://generativelanguage.googleapis.com"
ollama = "http://127.0.0.1:11434"
```

Add named gateways:

```toml
[upstreams]
deepseek = "https://api.deepseek.com"
deepseek-anthropic = { url = "https://api.deepseek.com/anthropic", kind = "anthropic", cache_hints = false }
openrouter = { url = "https://openrouter.ai/api", kind = "openai", usage = "openrouter", cost_source = "provider" }
gemini-openai = { url = "https://generativelanguage.googleapis.com/v1beta/openai", kind = "openai", usage = "gemini-openai" }
ollama-openai = { url = "http://127.0.0.1:11434/v1", kind = "openai" }
```

Named upstream URL:

```text
http://127.0.0.1:8787/u/<name>
```

The proxy resolves only names configured in your file.

## 7. Point a client at the proxy

Use `ctxoptimizer env --shell powershell` (or `bash`, `zsh`, `fish`) to print
ready-to-paste exports.

### OpenAI SDK / Chat Completions / Aider / Cline / Continue

```powershell
$env:OPENAI_BASE_URL = "http://127.0.0.1:8787/v1"
```

### Anthropic SDK / Claude Code

```powershell
$env:ANTHROPIC_BASE_URL = "http://127.0.0.1:8787"
```

### OpenCode

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "ctxoptimizer-deepseek": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "DeepSeek via ctxoptimizer",
      "options": { "baseURL": "http://127.0.0.1:8787/u/deepseek" },
      "models": { "deepseek-flash": { "name": "DeepSeek Flash" } }
    }
  }
}
```

### DeepSeek

- OpenAI surface: `http://127.0.0.1:8787/u/deepseek`
- Claude Code surface: `ANTHROPIC_BASE_URL=http://127.0.0.1:8787/u/deepseek-anthropic`

### OpenRouter

```powershell
$env:OPENAI_BASE_URL = "http://127.0.0.1:8787/u/openrouter"
```

### Native Gemini

Use a named Gemini upstream and point the Gemini client at:

```text
http://127.0.0.1:8787/u/gemini
```

The native `generateContent`/`streamGenerateContent` paths are forwarded as-is.

### Native Ollama

Point the Ollama client at:

```text
http://127.0.0.1:8787/u/ollama
```

`/api/chat` and `/api/generate` are supported, including NDJSON usage.

## 8. Choose a mode

| Mode | Behavior |
|---|---|
| `passthrough` | Forward unchanged; no transforms. |
| `shadow` | Run/measure/simulate transforms; forward original bytes. |
| `active` | Apply enabled transforms; retry original on 400/422. |

Start with `shadow`:

```powershell
ctxoptimizer run --mode shadow
```

Switch at runtime (requires a proxy started by `ctxoptimizer run`):

```powershell
ctxoptimizer mode active
ctxoptimizer mode shadow
```

Or per request:

```text
x-ctxoptimizer-mode: active
x-ctxoptimizer-bypass: 1
```

## 9. Verify traffic and cost

```powershell
ctxoptimizer status
ctxoptimizer stats
ctxoptimizer stats --json
ctxoptimizer stats --since 24h --project demo
ctxoptimizer export --format json --since 7d --out requests.json
ctxoptimizer export --format csv --since 7d --out requests.csv
```

The dashboard pages:

- **Overview** — spend, simulated baseline, waste, cache ratio, projects/models.
- **Live** — SSE-updated sessions, burn rate and recent requests.
- **Sessions / Requests** — turn-by-turn usage, timing, transform reports and diff viewer.
- **Waste** — W1–W8 findings, status controls and recommendations.
- **Transforms** — enable/disable, stats, quarantine history, expand usage and
  stale-elision break-even.
- **Pricing** — row editor + validated JSON override, unpriced models.
- **Settings** — mode, privacy/capture, license, config hash.
- **Doctor** — local checks.

## 10. Active mode safety

- Every transform runs in a journal; exceptions revert that transform.
- A no-regression guard discards changes that do not save enough tokens.
- A 400/422 retry sends the original bytes once and records `fallback_used`.
- The guard quarantines a transform per session after repeated fallbacks,
  low savings, expand errors or our-fault drift.
- `ctxoptimizer guard status`; `ctxoptimizer guard enable <transform>`; `ctxoptimizer guard disable <transform>`.
- `stale_result_elision` and `cache_serve` are opt-in. Use the break-even
  estimator before enabling them.

Check the dashboard **Transforms** page after switching to active.

## 11. MCP `ctxoptimizer_expand`

If a transform omits content, an MCP-capable agent can retrieve the original:

```powershell
ctxoptimizer mcp snippet --client claude-code
ctxoptimizer mcp run
```

Example registration:

```json
{
  "mcpServers": {
    "ctxoptimizer": {
      "command": "ctxoptimizer",
      "args": ["mcp", "run"]
    }
  }
}
```

Blobs are local, content-addressed and require capture not to be `off`.

## 12. Capture, privacy and purge

Payload capture is controlled by:

```toml
[telemetry]
capture_payloads = "changed_blocks" # off | changed_blocks | full
retention_days = 14
redact_secrets = true
```

- `off` stores nothing.
- `changed_blocks` stores the before/after of changed blocks.
- `full` stores request/final-request/response fixtures.

Captured text is redacted before storage. See `docs/privacy.md`.

Wipe everything:

```powershell
ctxoptimizer purge --all
```

## 13. Updating

Use the package manager that installed ctxoptimizer:

```powershell
uv tool upgrade ctxoptimizer
# or
pipx upgrade ctxoptimizer
```

There is no built-in self-update command. Updates come from the package index or
GitHub release channel; verify release checksums and only install from the
official source. See `docs/updating.md`.

## 14. License

ctxoptimizer is free and open-source software licensed under the **MIT License**.
See `LICENSE` and `NOTICE`.

## 15. Run at login

```powershell
ctxoptimizer service install --dry-run
ctxoptimizer service install
ctxoptimizer service uninstall
```

Supported: launchd (macOS), systemd `--user` (Linux), Windows scheduled task.

## 16. Troubleshooting

| Symptom | Fix |
|---|---|
| `ctxoptimizer: command not found` | Add `%USERPROFILE%\.local\bin` (Windows) or `~/.local/bin` to PATH; restart the shell. |
| Dashboard returns 401 | Open the URL with the per-run `?token=...` printed by `ctxoptimizer run`. |
| Dashboard returns 403 | Host header is not allowed; use `127.0.0.1`/`localhost` or configure `allow_remote`. |
| Port 8787 in use | `ctxoptimizer run --port 8788` and update client base URLs. |
| Upstream 401/403 | The client's provider key is wrong or missing; ctxoptimizer forwards it unchanged. |
| Upstream 429 | Provider rate limit; ctxoptimizer passes it through verbatim. |
| Transform fallbacks | Check Transforms page; guard may quarantine; inspect request detail. |
| No cache hits | Check Waste/drift; look for changing system prompt/tools/history. |
| `ctxoptimizer status` fails | Proxy not running, wrong port, or firewall; try the printed URL. |

Diagnostics:

```powershell
ctxoptimizer doctor --offline
ctxoptimizer doctor
```

## 17. Uninstall

```powershell
ctxoptimizer service uninstall
ctxoptimizer purge --all
uv tool uninstall ctxoptimizer
```

Remove the config directory manually if you want a completely clean uninstall:

```text
%LOCALAPPDATA%\ctxoptimizer\ctxoptimizer\
```

## 18. Quick command reference

```text
ctxoptimizer run [--host --port --mode --config]
ctxoptimizer status
ctxoptimizer mode passthrough|shadow|active
ctxoptimizer env --shell bash|zsh|fish|powershell
ctxoptimizer doctor [--offline]
ctxoptimizer stats [--since --project --json]
ctxoptimizer export --format json|csv [--since --out]
ctxoptimizer waste [--summary --json]
ctxoptimizer recommend [--json]
ctxoptimizer guard status|enable|disable <transform>
ctxoptimizer replay <request.json>
ctxoptimizer bench
ctxoptimizer capture --out <dir>
ctxoptimizer purge --all
ctxoptimizer mcp run
ctxoptimizer mcp snippet --client claude-code
ctxoptimizer service install|uninstall
```
