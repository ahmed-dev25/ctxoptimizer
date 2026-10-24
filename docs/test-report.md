# Test report (2026-10-25)

Command: `uv run pytest -q`

```text
252 passed, 1 warning in 17.60s
```

Warnings: Starlette `TestClient` deprecation for `httpx` (upstream package;
does not affect the proxy).

Other gates:

| Gate | Result |
|---|---|
| `uv run ruff check .` | pass |
| `uv run ruff format --check .` | pass |
| `uv run mypy --strict src` | pass (63 source files) |
| `uv build --wheel` | pass |
| `ctxproxy --version` | `0.1.0` |

## Coverage map

- Unit: transforms, SSE/NDJSON parsers, pricing, segments/drift, waste W1–W8,
  guard, cache_serve, stale elision, adapters (Anthropic/OpenAI/Gemini/Ollama),
  store, config, routing, CLI, dashboard/admin security, service/license.
- Integration: real fake upstream + uvicorn proxy, streaming byte equality,
  usage extraction, disconnect, retries, non-stream usage, persistence.
- Property: usage fuzz tests (`hypothesis`) never raise.
- Live contract tests (`-m live`) are opt-in and require real keys; they are not
  part of the default run.

## Known gaps

- No live Gemini/Ollama captures yet; documented shapes are exercised
  (see `docs/provider-notes.md` §11).
- Full dashboard charting is intentionally lightweight (server-rendered tables
  + a simple spend bar); no external chart/CDN assets.
- PyInstaller binaries are built in CI but are not signed/notarized here.
- Coverage is reported but not enforced by a threshold.
