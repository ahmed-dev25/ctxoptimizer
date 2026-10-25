# ctxproxy — Milestone Plan (P0 + P1)

**Status:** P1 complete (2026-10-25); P2 next · **Created:** 2026-10-24 · **Owner:** ahmed
**Scope source:** `SPEC.md` §22 (authoritative). This document turns the P0/P1
roadmap items into an execution sequence and records the deviations agreed for
this build. Live status, commits and branch state live in `docs/progress.md`.

---

## 1. Scope

| Phase | Deliverable |
|---|---|
| P0 | Repo scaffolding, validated configuration, core models/logging, test infrastructure |
| P1 | Transparent proxy including named upstreams for Anthropic/OpenAI-compatible providers, ground-truth telemetry, pricing, SQLite store, basic CLI |

**Milestone end state:** a local proxy running in `passthrough` mode that records
provider-reported usage and cost for providers with captured traffic, and honestly
reports `usage_source="none"` for providers whose traffic has not been captured yet.

### Out of scope for this milestone

Transforms and the pipeline (§12), drift detection (§13.4), waste detectors (§13.6),
baseline simulator (§13.5), active mode, dashboard (§16), MCP expand server
(§12.13), Gemini/Ollama adapters, cache hints, and
stale-result elision. No request body is ever mutated in this milestone; INV-2
(passthrough on unchanged) is therefore trivially satisfied.

## 2. Confirmed decisions

| # | Decision | ADR |
|---|---|---|
| 1 | Keep `uv_build`; `requires-python >=3.11`; dev on 3.14; CI on 3.11 + 3.14 | 0001 |
| 2 | Repo-local identity `ahmed` / `ahmed.devv25@gmail.com`; merge `--no-ff` per task | 0001 |
| 3 | Open-source MIT license; no activation checks | 0009 |
| 4 | Seven settings missing from §7.2 get documented defaults | 0003 |
| 5 | Provider fixtures come from real captures only; no invented fixtures | 0004 |
| 6 | Provider docs are researched in P1 and dated in `docs/provider-notes.md` | — |
| 7 | CI is committed now but stays dormant until a remote exists | 0001 |
| 8 | Documented-shape fixtures are allowed when sourced and dated | 0005 |
| 9 | Protocol-first provider support; named upstreams + per-upstream profiles | 0006 |

## 3. Environment

| Item | Value |
|---|---|
| OS | Windows 11 |
| Python | 3.14.7 (`.python-version`) |
| uv | 0.13.1 |
| git | 2.56.0 (`C:\Program Files\Git\cmd\git.exe`) |

The running OpenCode process started before git was added to PATH. Use the full
path until OpenCode is restarted.

## 4. Execution sequence

Tasks are strictly sequential: one branch, one gate run, one merge at a time.

| Order | Task | Depends on | Branch |
|---:|---|---|---|
| 1 | P0-1 Toolchain + skeleton | bootstrap | `feat/p0-1-toolchain` |
| 2 | P0-2 Config | P0-1 | `feat/p0-2-config` |
| 3 | P0-3 Models, logging, ULID | P0-1 | `feat/p0-3-models-logging` |
| 4 | P0-4 Test infrastructure | P0-1 | `feat/p0-4-test-infra` |
| 5 | P1-1 Routing + ingress | P0-2, P0-3 | `feat/p1-1-routing` |
| 6 | P1-7 Named upstreams + profiles | P1-1 | `feat/p1-7-upstreams` |
| 7 | P1-2 Proxy core | P1-1, P1-7 | `feat/p1-2-proxy-core` |
| 8 | P1-3 Usage parsers | documented shapes, P0-4 | `feat/p1-3-usage-parsers` |
| 9 | P1-8 Gateway usage quirks | P1-3 | `feat/p1-8-gateway-quirks` |
| 10 | P1-4 Pricing | P0-2, P1-8 | `feat/p1-4-pricing` |
| 11 | P1-5 Store | P0-2, P0-3 | `feat/p1-5-store` |
| 12 | P1-6 CLI | P1-2, P1-5 | `feat/p1-6-cli` |

P1-3 is deliberately last: parser code is written against real provider bytes
(SPEC §0.4). Until captures exist, `proxy.py` uses a null parser that records
`usage_source="none"`.

## 5. Task detail

### P0-1 — Toolchain + skeleton
**Deliverable:** `pyproject.toml` with runtime/dev dependencies and the
`ctxproxy.cli:app` entry point; ruff/mypy/pytest configuration; typed empty module
tree per SPEC §5; `.github/workflows/ci.yml`; smoke test.
**Files:** `pyproject.toml`, `src/ctxproxy/**`, `tests/conftest.py`,
`tests/unit/test_smoke.py`, `.github/workflows/ci.yml`.
**Tests:** package exposes version `0.4.1`; every module imports cleanly.
**DoD:** `ruff check`, `ruff format --check`, `mypy --strict src`, `pytest -q` pass;
`uv build` produces a wheel; `uv run ctxproxy --version` prints `0.1.0`.
**Note:** coverage is reported but not enforced while most modules are stubs.

### P0-2 — Config
**Deliverable:** pydantic v2 models for the full §7.2 config including the gap
defaults in §7 below; TOML load via `tomllib`; `CTXPROXY_*` env overrides; CLI
override merge; first-run config file creation with commented defaults;
`config_hash` = sha256 of the canonical effective transform config.
**Validation:** `target_bytes * 1.5 <= trigger_bytes`; `allow_remote` requires
`admin_token`; `cache_serve.enabled` requires `capture_payloads != "off"`; port
range; loopback host unless remote is allowed.
**Tests:** precedence matrix (CLI > env > file > default); invalid values rejected;
hash stable across re-loads and changes only when transform config changes.
**DoD:** all gates; a reload produces a new `config_hash` only for content changes.

### P0-3 — Models, logging, ULID
**Deliverable:** enums and dataclasses from SPEC §10 (`Provider`, `Endpoint`,
`Mode`, `RequestContext`, `ToolResultRef`, `TransformReport`, `Usage`,
`WasteFinding`); logging setup with an SEC-2 sanitizer (authorization, `x-api-key`,
`x-goog-api-key`, cookies, `key=` query params, `Bearer` tokens); stdlib ULID
helper (26-char Crockford base32, time-sortable) — no new dependency.
**Tests:** sanitizer positive and negative samples; ULID length, charset and
monotonic ordering; dataclass immutability where specified.
**DoD:** all gates; no secret appears in log output in any test.

### P0-4 — Test infrastructure
**Deliverable:** `tests/conftest.py` with a fake upstream Starlette app on an
ephemeral port, an SSE replay helper with configurable chunk sizes and delays,
an abrupt-disconnect mode, a golden-case runner (`UPDATE_GOLDEN=1`), and temp DB
fixtures.
**Tests:** the harness itself is exercised (chunking, disconnect, golden
regeneration) so later suites trust it.
**DoD:** all gates; a trivial integration request round-trips through the harness.

### P1-1 — Routing + ingress
**Deliverable:** `routing.py` implementing the §8.2 detection table;
`server.py` with `/p/<project>/**` and `/u/<upstream>/**` prefixes and
`/_ctxproxy/health`; query-string preservation; `x-ctxproxy-*` stripping;
absolute-URI target rejection (SEC-11).
**Tests:** every row of the detection table; prefix stripping; `?beta=true`,
Gemini `key=` and `alt=sse` preserved; unknown path -> default upstream
passthrough; health shape.
**DoD:** all gates.

### P1-2 — Proxy core
**Deliverable:** shared `httpx.AsyncClient` (HTTP/2, `trust_env`, no read timeout,
`follow_redirects=False`); hop-by-hop and recomputed header handling (§9.2);
`Accept-Encoding: identity` by default (§9.4); streaming tee via `aiter_raw()`;
client-disconnect handling that closes upstream and records
`outcome="client_disconnect"`; provider-shaped 502/504 bodies (§9.6); verbatim
upstream status/headers/body (INV-15); `<provider>_request_id` response header.
**Tests:** byte equality at 1/7/4096-byte chunking; disconnect closes upstream;
429 `retry-after` passes through; connect failure -> provider-shaped 502; auth
forwarded but absent from logs; no response buffering.
**DoD:** all gates; fake upstream observes exactly one request per client request.
**Note:** §9.7 retry-with-original is out of scope until transforms exist.

### P1-4 — Pricing
**Deliverable:** `data/pricing.json` with the §14.2 structure and one
Sonnet-class example entry marked `"verified": false`; `pricing.py` with
longest-literal-prefix glob matching, user override merge, unpriced model ->
`priced=0` and `NULL` costs; cost math including cache read and cache write.
**Tests:** table-driven matching; user override wins; unpriced path; cost math
for fresh/read/write/output.
**DoD:** all gates; prices are not invented beyond the spec example and every
entry is explicitly unverified.

### P1-5 — Store
**Deliverable:** `telemetry/store.py` with the §14.3 schema, `meta.schema_version`,
forward-only migrations with `.bak-<version>` backup, a single writer thread with
a bounded `queue.Queue(10000)`, batching (<= 100 rows or 250 ms), a dropped-events
counter, hourly retention, orphan-blob cleanup, `0600` on POSIX, and purge.
**Tests:** 20k-row burst does not block the caller > 5 ms; overflow increments the
counter; migration from a v0 fixture DB; retention deletes only expired rows.
**DoD:** all gates.

### P1-6 — CLI
**Deliverable:** typer commands `run`, `status`, `env`, `doctor` (basic), `export`
and `--version`; `env` prints shell-specific export lines; `doctor` checks port
availability, upstream reachability, DB writability, pricing staleness (> 60 days),
missing captures, loopback binding; README quickstart.
**Tests:** command help and exit codes; `env` output per shell; `export` JSON/CSV
shape; `doctor` reports the expected checks.
**DoD:** all gates; a manual end-to-end session through a real client records
usage if captures exist, otherwise `usage_source="none"`.

### P1-7 — Named upstreams + provider profiles
**Deliverable:** `[upstreams.<name>]` entries with `url`, `kind`, and a profile:
`usage` (`anthropic` | `openai` | `deepseek` | `openrouter` | `gemini-openai` | `ollama-openai`),
`cache_policy` (`explicit-anthropic` | `implicit-openai` | `automatic-deepseek` |
`gemini-implicit` | `none`), `cost_source` (`pricing` | `provider` | `none`),
`cache_hints` (bool), `inject_stream_usage` (bool).
`/u/<name>/**` routing strips the prefix and appends the remainder to the upstream URL.
Built-in profiles for anthropic, openai, deepseek, deepseek-anthropic, openrouter,
gemini and ollama.
**Tests:** named upstream resolution, unknown name -> 404, prefix stripping, query
preservation, profile defaults, and no provider-specific injection on third-party hosts.
**DoD:** all gates; `ctxproxy doctor` can resolve every configured upstream.

### P1-8 — Gateway usage quirks
**Deliverable:** usage extraction for DeepSeek (`prompt_cache_hit_tokens` /
`prompt_cache_miss_tokens`), OpenRouter (always-on final usage chunk, `cost`,
`cost_details.upstream_inference_cost`, content-free choice in the usage chunk,
`: OPENROUTER PROCESSING` comments), Gemini OpenAI-compat (final usage and
`stream_options` tolerance) and Ollama OpenAI-compat. Provider-reported cost surfaces
as `Usage.provider_cost_usd` and is preferred when `cost_source="provider"`.
**Tests:** doc-derived fixtures for DeepSeek and OpenRouter; usage accepted on any
chunk; comments ignored; provider cost recorded; `[DONE]` optional.
**DoD:** all gates; the DeepSeek-through-OpenCode smoke test records usage.

### P1-3 — Usage parsers
**Deliverable:** `telemetry/usage.py` with an incremental SSE splitter (CRLF,
split mid-event, split mid-UTF-8, comment lines, `data: [DONE]`), Anthropic
stream/non-stream, OpenAI chat with and without `include_usage`, OpenAI Responses
`response.completed`/`response.incomplete`, and normalization per §14.1 plus the
corrections in `docs/provider-notes.md` §5 (OpenAI `cache_write_tokens`,
Anthropic `thinking_tokens`, OpenAI TTL write buckets).
**Tests:** one suite per fixture; hypothesis fuzz feeding random bytes in random
chunk sizes with no exception and bounded memory.
**DoD:** all gates; parsers never raise into the forwarding path (INV-1/INV-3).
**Unblocked by:** the dated research in `docs/provider-notes.md`. Fixtures may
be derived from documented shapes under ADR 0005; live captures remain the
preferred validation and replace them when available.

## 6. Fixture contract (P1-3)

Required raw captures, bytes preserved exactly:

```
tests/fixtures/anthropic/messages_stream.sse
tests/fixtures/anthropic/messages_stream_cached.sse
tests/fixtures/anthropic/messages.json
tests/fixtures/openai/chat_stream_usage.sse
tests/fixtures/openai/chat_stream_no_usage.sse
tests/fixtures/openai/chat.json
tests/fixtures/openai/responses_stream.sse
tests/fixtures/openai/responses.json
tests/fixtures/deepseek/chat_stream_usage.sse
tests/fixtures/deepseek/chat.json
tests/fixtures/openrouter/chat_stream_usage.sse
tests/fixtures/openrouter/chat.json
```

Rules:
- Raw bytes from the wire, including CRLF and SSE framing.
- `tests/fixtures/**` is marked `-text` so git never rewrites line endings.
- Each provider folder gets a `meta.json` with the source. For a capture:
  capture date, client, model, and confirmation that prompts/secrets were
  sanitized. For a documented fixture: `"source": "documented"`, the source URL,
  the access date, and what the case exercises (ADR 0005).
- A documented fixture is never labelled a capture. Real captures supersede it.
- A missing provider stays on the null parser.

## 7. Config gap defaults (ADR 0003)

| Section | Key | Value | Spec ref |
|---|---|---|---|
| `guard` | `auto_reenable` | `0` (never auto-re-enable) | §12.14 |
| `guard` | `expand_error_rate` | `0.20` | §12.14 |
| `telemetry` | `max_blob_bytes` | `524288000` | §14.3 |
| `transforms.openai_hints` | `inject_stream_usage` | `false` | §11.2 |
| `transforms.duplicate_backref` | `include_never_touch` | `true` | §12.0.4 |
| `transforms.cache_serve` | `keep_recent_turns` | `12` | §12.12 |
| `waste.schema_bloat` | `enabled` | `true` (inert until P6) | §13.6 |
| `waste.schema_bloat` | `min_session_requests` | `10` | §13.7 |

## 8. Gates

Every task ends with:

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy --strict src
uv run pytest -q
```

Coverage is reported on every run. Enforcement starts at the end of P1: >= 80% on
the implemented modules and >= 90% on `telemetry/usage.py` once P1-3 lands.
`pip-audit` runs non-blocking until packaging (P7).

## 9. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| P1-2 streaming tee / disconnect semantics | Silent corruption or hangs | Byte-equality tests at 1/7/4096 bytes written before the code |
| Documentation drift in provider shapes | Parser mismatch | Dated `docs/provider-notes.md`, doc-derived fixtures, captures supersede when available |
| "OpenAI-compatible" is a spectrum | Wrong usage/cost on some gateways | Per-upstream profile + provider-reported cost; unknown shapes fall back to `source="none"` |
| Windows CRLF vs SSE fixtures | Tests exercise the wrong bytes | `tests/fixtures/** -text` + `core.autocrlf=false` |
| Stub modules drag coverage down | False red gates | Enforce coverage only on implemented modules |
| CI dormant (no remote) | Regressions not caught automatically | Local gates mandatory before every merge |
| `tiktoken` missing on 3.14 | No exact token counts | Optional extra; estimator degrades to `len/3.5` |

## 10. Deferred / follow-ups

- `data/cache_limits.json` — P4, needs verified provider thresholds.
- Blocking `pip-audit` gate — P7 packaging.
- `v0.1.0-alpha` tag at the end of P1 — optional, awaiting owner decision.
- Live contract tests (`pytest -m live`) — require owner-supplied keys.
- Live captures to validate the documented fixtures from ADR 0005.
- Coverage enforcement for transforms/analysis — when those modules exist.
