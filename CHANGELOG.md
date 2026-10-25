# Changelog

## 0.4.1 — 2026-10-25

- Distribution is now wheel/sdist only, published to PyPI with Trusted
  Publishing and PEP 740 attestations.
- Removed standalone PyInstaller binaries and the associated OS code-signing
  path.
- Release workflow publishes GitHub release checksums for the wheel/sdist and
  attests build provenance.
- CI no longer builds one-file binaries.

## 0.4.0 — 2026-10-25

- Relicensed ctxoptimizer under the **MIT License**.
- Removed activation checks, license CLI, license config and EULA.
- Removed the built-in self-update command and signing manifest; upgrade with
  `uv tool upgrade ctxoptimizer` or `pipx upgrade ctxoptimizer`.
- Source is intended to be public; see `NOTICE` for attribution/trademarks.

## 0.3.0-alpha — 2026-10-25

- Recommendation dismissal (30-day suppression) with dashboard controls.
- Per-row pricing editor with validated JSON fallback.
- Guard auto-re-enable, expand-error-rate and low-savings quarantine.
- CI coverage gate at 80% overall.
- Release workflow (wheel/sdist, checksums, unsigned binaries) and release
  checklist.
- Signed self-update (`ctxoptimizer update --check/update`) with Ed25519 + SHA-256
  verification.
- `volatile_normalizer` implemented and registered (opt-in).
- `openai_hints.inject_stream_usage` implemented (opt-in, api.openai.com only).
- MCP expand logging/counters and dashboard expand usage.
- Guard fallback counts use the configured moving window.
- Export JSON includes transform reports.
- Full capture mode writes request/final-request/response fixtures.
- DB schema v3 with automatic pre-migration backup; redacted request headers;
  per-transform fallback incidents; waste-over-time data.
- Golden corpus and transform invariant property tests added.

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
- MCP `ctxoptimizer_expand`; blob capture and purge.
- Admin security: Host allowlist, per-run token, CSRF, no CORS.
- Ed25519 offline license verification (enforcement off in this build).
- `ctxoptimizer service install/uninstall`, wheel + optional PyInstaller CI.
