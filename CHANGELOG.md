# Changelog

## 0.1.0 — 2026-10-25

Initial alpha.

- Config, routing (`/u/`, `/p/`, health), forwarding, streaming, provider-shaped
  errors, retry-with-original.
- Usage/cost for Anthropic, OpenAI Chat/Responses, DeepSeek, OpenRouter,
  native Gemini and native Ollama; SQLite telemetry and pricing table.
- Deterministic transforms: ANSI/progress/whitespace/line dedupe, smart
  truncate, duplicate backrefs, `cache_serve`, opt-in stale-result elision,
  Anthropic cache hints and OpenAI prompt-cache hints.
- Drift detection, waste W1–W8, recommendations, auto-quarantine guard.
- Dashboard: Overview, Live SSE, Sessions, Requests + diff, Waste controls,
  Transforms toggles/stats, Pricing editor, Settings, Doctor.
- MCP `ctxproxy_expand`; blob capture and purge.
- Admin security: Host allowlist, per-run token, CSRF, no CORS.
- Ed25519 offline license verification (enforcement off in this build).
- `ctxproxy service install/uninstall`, wheel + optional PyInstaller CI.
