# ctxproxy — Progress

**Last updated:** 2026-10-25
**Milestone:** P0–P7 — full spec (P1 complete; P2 in progress)
**Branch:** `feat/p2-3-pipeline`
**Overall:** P0 + P1 complete; 3 P2 tasks done

## Resume here

- **Last completed:** P2-3 pipeline framework (awaiting merge).
- **Last merge:** `d6b3c74` (P2-1/P2-2)
- **Next task:** P3-1/P3-2 transforms (`feat/p3-core-transforms`)
- **Blocked:** none
- **Active branch:** `feat/p2-3-pipeline` — merge to `main` before P3
- **Read first:** `SPEC.md` -> `docs/plan.md` -> this file -> `AGENTS.md`

## Smoke test (2026-10-25)

- **Client:** OpenCode 2.0.31, model `deepseek/deepseek-flash`,
  `opencode run --standalone`.
- **Route:** OpenCode -> `http://127.0.0.1:8787/u/deepseek` ->
  `https://api.deepseek.com`.
- **Config:** mode `shadow`, `capture_payloads = "off"`, temporary
  `opencode.json` override removed afterwards.
- **Result:** 3 requests, all `usage_source=provider` and
  `price_source=pricing`; OpenCode made side requests as well as the main turn.
- **Largest request:** 2.38 MB body, `fresh_input=331`,
  `cache_read=603264` (99.2% cache hit over the session), `output=267`,
  `reasoning=106`, `cost=$0.004039`, `ttfb=1175 ms`, `total=2797 ms`.
- **Session totals:** 3 requests, `$0.005393`, 4,630 fresh input,
  605,312 cache read, 310 output.
- **CLI verified:** `ctxproxy status`, `ctxproxy stats`, `ctxproxy export
  --format json`.
- **Notes:** DeepSeek peak rates were used; off-peak is half. `session_id` is
  `unknown` because OpenCode did not send `x-ctxproxy-session`; P2 derives
  sessions from content. No prompt content was stored (`capture_payloads=off`).
  The credential store was never read, and the temporary OpenCode config was
  removed.

## Status board

| ID | Task | Status | Branch | Commits | Merge | Gates | Notes |
|---|---|---|---|---|---|---|---|
| P0-1 | Toolchain + skeleton | done | `feat/p0-1-toolchain` | `c7c34c7` | `afdae28` | ruff, format, mypy, pytest (4) | `uv build` and `ctxproxy --version` verified |
| P0-2 | Config | done | `feat/p0-2-config` | `116adab` | `c37f4f7` | ruff, format, mypy, pytest (22) | default template round-trips to model defaults; wheel ships it |
| P0-3 | Models, logging, ULID | done | `feat/p0-3-models-logging` | `7428195` | `eea33ec` | ruff, format, mypy, pytest (38) | SEC-2 sanitizer + monotonic stdlib ULID |
| P0-4 | Test infrastructure | done | `feat/p0-4-test-infra` | `b24a59c` | `b509c9f` | ruff, format, mypy, pytest (45) | recording uvicorn fake upstream, SSE replay, golden runner |
| P1-1 | Routing + ingress | done | `feat/p1-1-routing` | `e045d48` | `7afda00` | ruff, format, mypy, pytest (75) | §8 table, `/p/`, `/u/`, health, mode headers |
| P1-7 | Named upstreams + profiles | done | `feat/p1-7-upstreams` | `4b2b148` | `ae06f94` | ruff, format, mypy, pytest (83) | built-in + override profiles, per-upstream cache policy |
| P1-2 | Proxy core | done | `feat/p1-2-proxy-core` | `4889ee7` | `10e90f8` | ruff, format, mypy, pytest (94) | streaming tee, disconnect, 502/504, header hygiene |
| P1-3 | Usage parsers | done | `feat/p1-3-usage-parsers` | `92721a5` | `3a78ef5` | ruff, format, mypy, pytest (112) | SSE decoder, Anthropic/OpenAI chat/Responses, doc fixtures, fuzz |
| P1-8 | Gateway usage quirks | done | `feat/p1-8-gateway-quirks` | `05d2fb9` | `6f20a24` | ruff, format, mypy, pytest (119) | DeepSeek cache fields, OpenRouter cost/comments, Gemini/Ollama compat |
| P1-4 | Pricing | done | `feat/p1-4-pricing` | `0719d9a` | `be61b57` | ruff, format, mypy, pytest (130) | verified rates, provider cost, specificity, TTL buckets |
| P1-5 | Store | done | `feat/p1-5-store` | `0e3496f` | `3ae9fea` | ruff, format, mypy, pytest (139) | writer thread, WAL, overflow, prune, migration |
| P1-6 | CLI | done | `feat/p1-6-cli` | `689bbb8` | `b8769c1` | ruff, format, mypy, pytest (149) | run/status/env/doctor/stats/export/purge |
| P2-1 | Adapters, segments, session | done | `feat/p2-1-adapters` | recorded at merge | — | ruff, format, mypy, pytest (156) | Anthropic/OpenAI chat/Responses structure access |
| P2-2 | Token estimation | done | `feat/p2-1-adapters` | recorded at merge | — | ruff, format, mypy, pytest (156) | tiktoken-optional estimator + EMA calibrator |
| P2-3 | Pipeline framework | done | `feat/p2-3-pipeline` | recorded at merge | — | ruff, format, mypy, pytest (161) | journal, no-regress, budget, shadow flag |
| P2-4 | Drift detector | todo | — | — | — | — | — |
| P2-5 | Baseline simulator | todo | — | — | — | — | — |
| P2-6 | Dashboard v0 | todo | — | — | — | — | — |
| P2-7 | Waste W1–W2 | todo | — | — | — | — | — |
| P2-8 | Waste W3–W6 | todo | — | — | — | — | — |

Status vocabulary: `todo` -> `in-progress` -> `blocked` -> `review` -> `done`.
Rows are in execution order; see `docs/plan.md` §4.

## Gate log

| Date | Task | ruff | mypy | pytest | coverage | Commit |
|---|---|---|---|---|---|---|
| 2026-10-24 | bootstrap | n/a (docs only) | n/a | n/a | n/a | `5b3f61b` |
| 2026-10-24 | P0-1 | pass | pass (50 files) | 4 passed | reported, not enforced | `c7c34c7` |
| 2026-10-24 | P0-2 | pass | pass (50 files) | 22 passed | reported, not enforced | `116adab` |
| 2026-10-24 | P0-3 | pass | pass (50 files) | 38 passed | reported, not enforced | `7428195` |
| 2026-10-24 | P0-4 | pass | pass (50 files) | 45 passed | reported, not enforced | `b24a59c` |
| 2026-10-24 | P1-1 | pass | pass (50 files) | 75 passed | reported, not enforced | `e045d48` |
| 2026-10-24 | P1-7 | pass | pass (51 files) | 83 passed | reported, not enforced | `4b2b148` |
| 2026-10-25 | P1-2 | pass | pass (51 files) | 94 passed | reported, not enforced | `4889ee7` |
| 2026-10-25 | P1-3 | pass | pass (52 files) | 112 passed | reported, not enforced | `92721a5` |
| 2026-10-25 | P1-8 | pass | pass (52 files) | 119 passed | reported, not enforced | `05d2fb9` |
| 2026-10-25 | P1-4 | pass | pass (52 files) | 130 passed | reported, not enforced | `0719d9a` |
| 2026-10-25 | P1-5 | pass | pass (52 files) | 139 passed | reported, not enforced | `0e3496f` |
| 2026-10-25 | P1-6 | pass | pass (52 files) | 149 passed | reported, not enforced | `689bbb8` |
| 2026-10-25 | P2-1/2 | pass | pass (52 files) | 156 passed | reported, not enforced | recorded at merge |
| 2026-10-25 | P2-3 | pass | pass (52 files) | 161 passed | reported, not enforced | recorded at merge |
| 2026-10-25 | smoke | live OpenCode -> DeepSeek | n/a | manual | 3 rows, 99.2% cache hit, $0.005393 | `312bb3a` |

## Changelog

- 2026-10-24 — Bootstrap: `git init -b main`, repo-local identity
  (`ahmed` / `ahmed.devv25@gmail.com`), `core.autocrlf=false`,
  `.gitignore`, `.gitattributes`, `docs/` tree, ADRs 0001-0004, `AGENTS.md`,
  README. Architecture HTML moved to `docs/architecture.html`.
- 2026-10-24 — P0-1: `pyproject.toml` with runtime/dev dependencies and the
  `ctxproxy.cli:app` entry point, ruff/mypy/pytest/coverage config, typed module
  tree for the full SPEC layout, CI workflow (dormant), smoke tests.
  Added `pytest-cov` (needed for the §20.2 coverage gate; not in the §6 list)
  and excluded `SPEC.md` from ruff because ruff 0.17 reformats Python code
  blocks inside Markdown. `uv.lock` committed.
- 2026-10-24 — P0-2: pydantic v2 models for the full §7.2 config plus the eight
  gap defaults from ADR 0003; CLI > env > file > defaults precedence;
  `config_hash` scoped to transforms/tools/pipeline; unknown-key reporting;
  first-run creation from `data/default_config.toml`, verified to ship in the
  wheel.
- 2026-10-24 — P0-3: §10 enums and dataclasses, SEC-2 header/URL sanitizer with
  `configure_logging`, and a dependency-free monotonic ULID generator.
- 2026-10-24 — P0-4: shared test harness — recording uvicorn fake upstream on an
  ephemeral loopback port, SSE replay with chunking/delays/abrupt cut, client
  disconnect observation, golden runner with `UPDATE_GOLDEN=1`, and temp DB/data
  fixtures. Phase 0 complete.
- 2026-10-24 — Provider research: dated wire formats and usage schemas for
  Anthropic Messages, OpenAI Chat Completions and OpenAI Responses, sourced from
  official docs and official SDK types (`docs/provider-notes.md`). Found three
  spec corrections: OpenAI `fresh_input` must also subtract
  `cache_write_tokens`; Anthropic now exposes
  `output_tokens_details.thinking_tokens`; OpenAI GPT-5.6+ has 30m/12h
  cache-write buckets and rates. P1-3 unblocked under ADR 0005.
- 2026-10-24 — Provider scope: added P1-7 (named upstreams + profiles) and P1-8
  (gateway usage quirks) after research into DeepSeek, OpenRouter, OpenCode,
  Gemini-compat and Ollama-compat. Protocol-first support (ADR 0006); no
  cross-provider routing or translation. Open questions recorded in
  `docs/open-questions.md`.
- 2026-10-24 — P1-1: pure routing layer (§8.2 table, `/p/`, `/u/`, mode and
  bypass headers, client UA detection), Starlette ingress with injectable
  forwarder, `/_ctxproxy/health`, absolute-form target rejection, named-upstream
  resolution and query preservation.
- 2026-10-24 — P1-7: per-upstream profiles (`usage`, `cache_policy`,
  `cost_source`, `cache_hints`, `inject_stream_usage`) with built-ins for
  anthropic/openai/gemini/ollama/deepseek/deepseek-anthropic/openrouter/
  gemini-openai/ollama-openai; string and table entries resolve through one
  registry; routing carries the profile.
- 2026-10-25 — P1-2: forwarding core with shared httpx client, hop-by-hop and
  `x-ctxproxy-*` stripping, `Accept-Encoding: identity`, byte-true streaming via
  `aiter_raw`, side-channel null usage parser, client-disconnect closure,
  provider-shaped 502/504, verbatim upstream status/headers/body, request ids and
  runtime counters.
- 2026-10-25 — P1-3: byte-buffered WHATWG SSE decoder (CR/LF/CRLF, comments,
  multi-line data, BOM, split UTF-8, bounded frames) and streaming parsers for
  Anthropic (cumulative delta semantics, TTL breakdown, thinking tokens), OpenAI
  Chat and OpenAI Responses; non-stream body parsers; doc-derived fixtures for
  Anthropic/OpenAI/DeepSeek/OpenRouter; hypothesis totality tests.
- 2026-10-25 — P1-8: gateway quirks — DeepSeek cache hit/miss fields, OpenRouter
  always-on usage plus provider-reported cost and content-free usage chunk,
  Gemini OpenAI-compat usage, Ollama OpenAI-compat estimates, optional `[DONE]`,
  and mid-stream error tolerance.
- 2026-10-25 — P1-4: verified pricing table for Anthropic, OpenAI, DeepSeek and
  Gemini with current source URLs and dates; provider-scoped specificity
  matching; Anthropic 5m/1h and OpenAI 30m/12h cache-write buckets; OpenRouter
  provider-reported cost takes precedence; unknown models stay unpriced; proxy
  records model, cost and price source per request.
- 2026-10-25 — P1-5: WAL SQLite schema (requests/sessions/children), one bounded
  writer thread with 100-row/250 ms batching, drop-with-counter overflow,
  forward-only schema versioning, retention/purge, request persistence from the
  proxy, and a 20k-row burst test.
- 2026-10-25 — P1-6: CLI `run`, `status`, `env` (bash/zsh/fish/powershell),
  `doctor` (bind/db/pricing/port/tiktoken/upstreams), `stats`, `export`
  (JSON/CSV, `--since`), and `purge`; `docs/client-setup.md` with recipes for
  Claude Code, OpenCode, DeepSeek, OpenRouter, Codex, Aider, Gemini-compat and
  Ollama-compat.
- 2026-10-25 — Live smoke test: OpenCode 2.0.31 -> ctxproxy `/u/deepseek` ->
  DeepSeek `deepseek-flash`. 3 requests, provider usage, 99.2% cache hit,
  `$0.005393` total, CLI status/stats/export verified. Temporary OpenCode config
  removed; no prompts stored.
- 2026-10-25 — P2-1/P2-2: Anthropic/OpenAI Chat/OpenAI Responses adapters with
  tool-result handles, canonical segments/hashes, system/first-user/tool-name
  extraction, session derivation + project detection, key fingerprinting, and a
  tiktoken-optional token estimator with EMA calibration.
- 2026-10-25 — P2-3: transform protocol, pure-text driver, ordered pipeline with
  per-transform journal/restore, exception isolation, time budget, no-regress
  guard and shadow flag.

## Handoff notes

- `git` is installed at `C:\Program Files\Git\cmd\git.exe` but is not on the
  running OpenCode process PATH. Invoke it by full path until OpenCode restarts.
- The system git config sets `core.autocrlf=true`; this repo overrides it to
  `false` and normalizes via `.gitattributes`.
- No remote is configured yet, so `.github/workflows/ci.yml` is dormant.
- No live provider captures exist yet. P1-3 may use documented fixtures with a
  `meta.json` source (ADR 0005); captures replace them when available.
- Run `uv sync --extra dev` after cloning; `uv.lock` is committed.
- Ruff formats Python code blocks inside Markdown. `SPEC.md` is excluded in
  `pyproject.toml`; do not remove that exclusion.
