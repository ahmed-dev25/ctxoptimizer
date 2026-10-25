# Client setup

Point a client at the proxy by changing its base URL. The proxy does not
translate protocols: use the surface the provider already speaks.

Start the proxy first:

```powershell
uv run ctxproxy run
# or: uv tool install ctxproxy && ctxproxy run
```

Print ready-to-paste exports:

```powershell
ctxproxy env --shell powershell   # bash | zsh | fish | powershell
```

## Claude Code (Anthropic surface)

```powershell
$env:ANTHROPIC_BASE_URL = "http://127.0.0.1:8787"
```

Claude Code already sends `cache_control`; the proxy will not double-inject.

## OpenAI SDK and Chat Completions clients

```powershell
$env:OPENAI_BASE_URL = "http://127.0.0.1:8787/v1"
```

## OpenCode

OpenCode v2 uses the AI SDK. Add a custom provider in `opencode.json` (global or
project) and choose its model with `/models`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "ctxproxy-deepseek": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "DeepSeek via ctxproxy",
      "options": { "baseURL": "http://127.0.0.1:8787/u/deepseek" },
      "models": { "deepseek-flash": { "name": "DeepSeek Flash" } }
    }
  }
}
```

For Responses-based providers use `"npm": "@ai-sdk/openai"` and a base URL that
ends at `/u/<name>/v1` (for example `/u/openai/v1`).

## DeepSeek

Add the upstream to your config (first-run config lives at
`%LOCALAPPDATA%\ctxproxy\config.toml` on Windows, `~/.config/ctxproxy/config.toml`
on Linux/macOS):

```toml
[upstreams]
deepseek = "https://api.deepseek.com"
deepseek-anthropic = { url = "https://api.deepseek.com/anthropic", kind = "anthropic", cache_hints = false }
```

- OpenAI surface: base URL `http://127.0.0.1:8787/u/deepseek`.
- Claude Code surface: `ANTHROPIC_BASE_URL=http://127.0.0.1:8787/u/deepseek-anthropic`
  with a DeepSeek API key. DeepSeek maps `claude-*` model names to its own models
  and ignores `cache_control`.

## OpenRouter

```toml
[upstreams]
openrouter = { url = "https://openrouter.ai/api", kind = "openai", usage = "openrouter", cost_source = "provider" }
```

Base URL: `http://127.0.0.1:8787/u/openrouter`. OpenRouter always reports usage
and its own cost; the proxy records that provider cost instead of table pricing.

## Codex CLI

Codex uses the OpenAI Responses API. Its base-URL configuration is still marked
VERIFY in `SPEC.md`; when it honors a custom URL, use
`http://127.0.0.1:8787/v1`. ChatGPT-OAuth builds that bypass the base URL cannot
be proxied.

## Aider, Cline, Continue, Kilo

Use the OpenAI-compatible base URL `http://127.0.0.1:8787/v1` (or
`http://127.0.0.1:8787/u/<name>` for a named upstream) in the client's custom
endpoint setting.

## Gemini (OpenAI-compatible)

```toml
[upstreams]
gemini-openai = { url = "https://generativelanguage.googleapis.com/v1beta/openai", kind = "openai", usage = "gemini-openai" }
```

Base URL: `http://127.0.0.1:8787/u/gemini-openai`. Native Gemini
`generateContent`/`streamGenerateContent` is supported via `/u/gemini`.

## Ollama

For the OpenAI-compatible surface, add
`ollama-openai = { url = "http://127.0.0.1:11434/v1", kind = "openai" }` and use
`http://127.0.0.1:8787/u/ollama-openai`. Native `/api/chat` and `/api/generate`
are supported via `/u/ollama`.

## First-run privacy

The proxy defaults to `shadow` (observe only) and forwards request bodies
unchanged. For a live smoke test, set `capture_payloads = "off"` under
`[telemetry]` so prompts are never stored. Credentials are forwarded and never
logged or persisted.
