# Configure this repository to use ctxoptimizer

This file is a self-contained setup checklist for a coding agent working in a
new repository. The goal is to route this repository's LLM traffic through a
locally running `ctxoptimizer` proxy and to tag the traffic with a project name
so its usage and savings can be measured separately.

`ctxoptimizer` is a **global local proxy**, not a per-repository package. Do not
copy ctxoptimizer's source or config into this repository. Only the client
configuration in this repository may need to change.

## Agent rules

- Do not print, commit, or ask for real API keys.
- Do not overwrite unrelated client configuration; merge changes.
- Do not commit `.env` files containing secrets.
- If the client or upstream is unknown, inspect the repository and ask one
  concise question before guessing.
- Keep the proxy on loopback. Do not enable `allow_remote`.
- Prefer `shadow` mode first; switch to `active` only after a successful test.
- If a process cannot be kept alive in the current session, ask the user to run
  `ctxoptimizer run` in a separate terminal or install it as a background
  service. Do not block the agent session forever.

## 1. Identify the client and provider

Determine which client this repository uses, for example:

- Claude Code / Anthropic SDK
- OpenAI SDK, Aider, Cline, Continue, Kilo, or another OpenAI-compatible client
- OpenCode
- Codex CLI
- Native Gemini or Ollama
- A named gateway such as DeepSeek or OpenRouter

Determine the upstream protocol and model provider. The proxy does not translate
protocols, so the client must already speak the provider's protocol.

## 2. Check that ctxoptimizer is installed

```powershell
ctxoptimizer --version
```

If the command is not found, install it globally:

```powershell
uv tool install ctxoptimizer
# or
pipx install ctxoptimizer
```

After installation, reopen the terminal if the command is still not found.
Useful locations:

- Windows: `%USERPROFILE%\.local\bin\ctxoptimizer.exe`
- Linux/macOS: `~/.local/bin/ctxoptimizer`

Confirm:

```powershell
ctxoptimizer --version
```

## 3. Start the proxy

Check whether it is already running:

```powershell
ctxoptimizer status
```

If it is not running, start it in a separate terminal:

```powershell
ctxoptimizer run
```

For a persistent per-user service:

```powershell
ctxoptimizer service install --dry-run
ctxoptimizer service install
```

Defaults:

- Address: `http://127.0.0.1:8787`
- Mode: `shadow` (measure and simulate; forward original bytes)

Use another port only if necessary:

```powershell
ctxoptimizer run --port 8788
```

If the port changes, use the same port in every client URL below.

## 4. Choose a project ID

Use a stable, URL-safe repository identifier, for example `my-project` or the
repository directory name.

The project segment is:

```text
/p/<project-id>/
```

This is optional, but strongly recommended so usage can be filtered per
repository. Do not put spaces or `/` in the project ID.

## 5. Configure the client

Use the client's native base-URL setting. The proxy does not read `.env`; only
the client does, so `.env` works only if the client explicitly loads it.

### Claude Code / Anthropic

Shell:

```powershell
$env:ANTHROPIC_BASE_URL = "http://127.0.0.1:8787/p/my-project"
```

`.env` equivalent:

```dotenv
ANTHROPIC_BASE_URL=http://127.0.0.1:8787/p/my-project
```

For a named Anthropic-compatible upstream, append `/u/<name>`:

```powershell
$env:ANTHROPIC_BASE_URL = "http://127.0.0.1:8787/p/my-project/u/deepseek-anthropic"
```

### OpenAI SDK / Aider / Cline / Continue / other OpenAI-compatible clients

Shell:

```powershell
$env:OPENAI_BASE_URL = "http://127.0.0.1:8787/p/my-project/v1"
```

`.env` equivalent:

```dotenv
OPENAI_BASE_URL=http://127.0.0.1:8787/p/my-project/v1
```

For a named OpenAI-compatible upstream such as DeepSeek or OpenRouter, use the
upstream base URL documented for that provider:

```text
http://127.0.0.1:8787/p/my-project/u/deepseek
http://127.0.0.1:8787/p/my-project/u/openrouter
```

### OpenCode

Merge a provider into the repository's `opencode.json` (or the user's global
OpenCode config). Preserve the existing providers and schema.

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "ctxoptimizer-deepseek": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "DeepSeek via ctxoptimizer",
      "options": {
        "baseURL": "http://127.0.0.1:8787/p/my-project/u/deepseek"
      },
      "models": {
        "deepseek-flash": {
          "name": "DeepSeek Flash"
        }
      }
    }
  }
}
```

Select the provider/model in OpenCode after adding it.

For an OpenAI Responses-based provider, use the appropriate AI SDK provider and
a base URL ending in `/u/<name>/v1` when required by that client.

### Codex CLI

Codex uses the OpenAI Responses API. If the installed Codex version honors a
custom base URL, set:

```powershell
$env:OPENAI_BASE_URL = "http://127.0.0.1:8787/p/my-project/v1"
```

ChatGPT-OAuth builds that bypass custom base URLs cannot be proxied. Verify the
actual behavior rather than assuming this works.

### Native Gemini and Ollama

Use the named upstream route documented by ctxoptimizer:

```text
http://127.0.0.1:8787/p/my-project/u/gemini
http://127.0.0.1:8787/p/my-project/u/ollama
```

The native `generateContent` / `streamGenerateContent`, `/api/chat`, and
`/api/generate` paths are forwarded as-is.

## 6. Keep provider keys unchanged

Do not move provider API keys into ctxoptimizer. Keep the client's existing
environment variables or credential store. ctxoptimizer forwards the client's
own `Authorization`, `x-api-key`, or `x-goog-api-key` headers and does not store
them.

Do not commit a `.env` containing keys. If the repository already has a safe
`.env.example`, document the base-URL variables there without real values.

## 7. Verify the setup

1. Confirm the proxy is healthy:

   ```powershell
   ctxoptimizer status
   ```

2. Make one small request through the client.

3. Check the request was recorded under the project:

   ```powershell
   ctxoptimizer stats --project my-project
   ```

4. Inspect the dashboard URL printed by `ctxoptimizer run` if needed.

If `stats` is empty:

- confirm the client is using the new base URL;
- confirm the project segment is spelled the same;
- confirm the proxy port matches;
- check whether the client bypasses custom base URLs (common with OAuth builds).

## 8. Choose the mode

Start in `shadow`:

```powershell
ctxoptimizer mode shadow
```

Shadow mode measures and simulates but forwards the original bytes.

After verifying the traffic and the dashboard, switch to active mode if
optimization is desired:

```powershell
ctxoptimizer mode active
```

Switch back immediately if the client reports errors or if transforms fall
back:

```powershell
ctxoptimizer mode shadow
```

A single request can override the mode with the header:

```text
x-ctxoptimizer-mode: active
```

## 9. Privacy and configuration

The global ctxoptimizer config is:

- Windows: `%LOCALAPPDATA%\ctxoptimizer\ctxoptimizer\config.toml`
- Linux/macOS: `~/.config/ctxoptimizer/config.toml`

Do not add this file to the repository.

Payload capture defaults to `changed_blocks`. For a privacy-sensitive
repository, set:

```toml
[telemetry]
capture_payloads = "off"
```

and reload/restart the proxy. Captured text is local, redacted on a best-effort
basis, and retained according to `retention_days`.

## 10. Rollback

To undo the client configuration:

- remove or restore the repository-local `.env` / client config entries;
- unset `ANTHROPIC_BASE_URL` and `OPENAI_BASE_URL` in the current shell;
- restore the client's original provider base URL.

Do not uninstall the global proxy or delete its data unless the user asks.

To stop a service installed by ctxoptimizer:

```powershell
ctxoptimizer service uninstall
```

## Acceptance checklist for the agent

- [ ] `ctxoptimizer --version` succeeds.
- [ ] The proxy is running on the expected port.
- [ ] The correct client surface was identified.
- [ ] The client base URL includes the intended `/p/<project>` segment.
- [ ] Existing provider API keys and unrelated client settings were preserved.
- [ ] A test request succeeds through the proxy.
- [ ] `ctxoptimizer stats --project <project>` shows the request.
- [ ] The mode is documented (`shadow` or intentionally `active`).
- [ ] No secrets or `.env` files were committed.
