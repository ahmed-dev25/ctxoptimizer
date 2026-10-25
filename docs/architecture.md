# Architecture

```text
client (Claude Code / OpenCode / SDK / ...)
        │  provider-native protocol, only base URL changed
        ▼
┌────────────────────────────────────────────────────────────┐
│ ctxoptimizer (loopback)                                        │
│                                                            │
│ routing.py       /u/<name>, /p/<project>, auto-detect       │
│ providers/       Anthropic, OpenAI Chat/Responses, Gemini,  │
│                  Ollama adapters (segments + tool refs)     │
│ analysis/        segments, session, drift, waste W1–W8,     │
│                  markers, recommendations                   │
│ transforms/      deterministic text edits + cache hints     │
│ pipeline.py      journal, no-regress, budget, shadow        │
│ proxy.py         forward, stream, usage, retry, blobs       │
│ telemetry/       SSE/NDJSON usage, pricing, SQLite writer   │
│ dashboard/       server-rendered pages + JSON admin API     │
│ mcp.py           ctxoptimizer_expand over stdio                 │
└────────────────────────────────────────────────────────────┘
        │  client credentials forwarded unchanged
        ▼
provider / gateway
```

## Request path

1. `classify` resolves the upstream, provider/endpoint, project and mode.
2. The body is parsed once; the adapter exposes tool-result handles and a
   canonical segment list (no provider layout leaks into transforms).
3. `run_pipeline` runs transforms in a fixed order, journals touched text,
   enforces the token-saving guard and time budget, and keeps shadow mutations
   out of forwarded bytes.
4. The request is forwarded with hop-by-hop headers stripped; the response is
   streamed raw while a side-channel parser reads usage.
5. On completion the request bundle is queued to one SQLite writer thread
   (bounded; drop-with-counter, never blocking) and blobs are written when
   capture is enabled.

## Stateful pieces

- `cache_serve` and `stale_result_elision` are opt-in and batch-boundary
  anchored (SPEC 12.8/12.12).
- `Guard` quarantines a transform per session after fallback/our-fault drift.
- `AnalysisState` keeps bounded per-session drift/waste state.
- Blobs are content-addressed files; `ctxoptimizer_expand` serves them by ref.

## Admin API

All routes are under `/_ctxoptimizer/api/`, versioned with `api_version: 1`, and
protected by Host allowlist + admin token + CSRF. Mutating routes accept JSON.
The dashboard pages use the same service layer; there is no SPA build step.

## Packaging

- Primary and only distribution: wheel/sdist via PyPI and `uv tool install` / `pipx`.
- No standalone PyInstaller binaries or OS code-signing step; PyPI Trusted
  Publishing and PEP 740 attestations cover package provenance.
- Autostart: `ctxoptimizer service install` writes a launchd plist, systemd --user
  unit, or Windows scheduled task.
