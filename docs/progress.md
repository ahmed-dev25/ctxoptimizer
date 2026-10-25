# ctxproxy — Progress

**Last updated:** 2026-10-25
**Milestone:** P0–P11 — MIT open-source release
**Branch:** `main`
**Overall:** P11 merged; history audit clean; old release/tag removed; ready to tag `v0.4.0`

## Resume here

- **Last completed:** P11 MIT relicense (`7ee05d9`) and history secret audit.
- **Last merge:** `123d8ee` (P11)
- **Next task:** tag `v0.4.0`, publish release assets/manifest, make the
  repository public.
- **Blocked:** none
- **Active branch:** none — working tree is on `main`
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
| P2-3 | Pipeline framework | done | `feat/p2-3-pipeline` | `b1de5ec` | `f829b6a` | ruff, format, mypy, pytest (161) | journal, no-regress, budget, shadow flag |
| P2-4 | Drift detector | done | `feat/p2-analysis` | `0959c09` | `f7fac41` | ruff, format, mypy, pytest (189) | 7 causes + tracker |
| P2-5 | Baseline simulator | done | `feat/p2-analysis` | `0959c09` | `f7fac41` | ruff, format, mypy, pytest (189) | explicit + implicit cache simulation |
| P2-6 | Dashboard v0 | done | `feat/p2-6-dashboard` | `399c962` | `f717c7b` | ruff, format, mypy, pytest (201) | overview + waste page + admin API |
| P2-7 | Waste W1–W2 | done | `feat/p2-analysis` | `0959c09` | `f7fac41` | ruff, format, mypy, pytest (189) | redundant re-read + identical output |
| P2-8 | Waste W3–W6 | done | `feat/p2-analysis` | `0959c09` | `f7fac41` | ruff, format, mypy, pytest (189) | fanout, runaway, recurring/params drift |
| P3-1 | ANSI/progress/whitespace | done | `feat/p3-core-transforms` | `67f538c` | `ad69997` | ruff, format, mypy, pytest (180) | pure functions + eligibility |
| P3-2 | Line dedupe | done | `feat/p3-core-transforms` | `67f538c` | `ad69997` | ruff, format, mypy, pytest (180) | exact + near-duplicate runs |
| P3-3 | Smart truncate | done | `feat/p3-core-transforms` | `67f538c` | `ad69997` | ruff, format, mypy, pytest (180) | head/tail/signal windows/markers |
| P3-4 | Duplicate backref | done | `feat/p3-core-transforms` | `67f538c` | `ad69997` | ruff, format, mypy, pytest (180) | later-copy stubs only |
| P3-5 | Active mode + retry + blobs | done | `feat/p3-core-transforms` | `67f538c` | `ad69997` | ruff, format, mypy, pytest (180) | active wiring, 400 retry, changed-block blobs |
| P3-7 | Auto-quarantine guard | done | `feat/p3-7-8-9` | `97f7d5f` | `8890137` | ruff, format, mypy, pytest (210) | fallback/drift quarantine + enable |
| P3-8 | `cache_serve` | done | `feat/p3-7-8-9` | `97f7d5f` | `8890137` | ruff, format, mypy, pytest (210) | batch-anchored, stateful, opt-in |
| P3-9 | MCP expand | done | `feat/p3-7-8-9` | `97f7d5f` | `8890137` | ruff, format, mypy, pytest (210) | stdio JSON-RPC + blob retrieval |
| P4-1 | Anthropic cache hints | done | `feat/p2-6-dashboard` | `399c962` | `f717c7b` | ruff, format, mypy, pytest (201) | 4-breakpoint stair-step |
| P4-2 | OpenAI hints | done | `feat/p2-6-dashboard` | `399c962` | `f717c7b` | ruff, format, mypy, pytest (201) | api.openai.com only |
| P4-3 | Marker quality metric | done | `feat/p5-dashboard` | recorded at merge | — | ruff, format, mypy, pytest (214) | markers + coverage in health/last request |
| P5 | Full dashboard | done | `feat/p5-p7-complete` | `e63ba16` | `67b4ff3` | ruff, format, mypy, pytest (252) | Overview/Live SSE/Session/Request+diff/Waste controls/Transforms toggles/Pricing editor/Settings/Doctor; admin token+Host+CSRF |
| P6-1 | Native Gemini adapter | done | `feat/p6-native` | `6c265cf` | `969d86b` | ruff, format, mypy, pytest (232) | telemetry + segments + string-leaf tool results |
| P6-2 | Native Ollama adapter | done | `feat/p6-native` | `6c265cf` | `969d86b` | ruff, format, mypy, pytest (232) | `/api/chat` NDJSON + `/api/generate` |
| P6-3 | Named OpenAI-compatible upstreams | done | `main` | earlier | — | pass | ADR 0006 profiles; no change needed |
| P6-4 | `stale_result_elision` | done | `feat/p6-native` | `6c265cf` | `969d86b` | ruff, format, mypy, pytest (232) | opt-in transform + break-even estimator API/UI |
| P6-5 | W7/W8 | done | `feat/p6-native` | `6c265cf` | `969d86b` | ruff, format, mypy, pytest (232) | W7 opt-in heuristic, W8 default on |
| P7 | Packaging/service/updates | done | `feat/p5-p7-complete` | `e63ba16` | `67b4ff3` | ruff, format, mypy, pytest (252) | wheel + PyInstaller CI, service install/uninstall, signed-update verification, docs |
| P8 | Hardening pass | done | `feat/p8-hardening` | `22814b6` | `279ea97` | ruff, format, mypy, pytest (266) | volatile normalizer, stream usage injection, expand counters, guard window, export reports, full capture fixtures, migration backup, redacted headers, golden/property tests |
| P9 | Hardening pass 2 | done | `feat/p9-hardening` | `3a34064` | `0ba10a2` | ruff, format, mypy, pytest (292), coverage 80.64% | recommendation suppression, row pricing editor, guard auto-re-enable/expand health, release workflow/checklist |
| P9-1 | Low-savings guard | done | `feat/p9-1-savings` | `58410ee` | `6173b3b` | ruff, format, mypy, pytest (292), coverage 80.64% | min_savings_to_stay over the guard window |
| P10 | Release prep | done | `feat/p10-release` | `ff54faa` | `f50a2cf` | ruff, format, mypy, pytest (292), coverage 80.64% | release artifacts, signed self-update, version `0.3.0`, release tooling |
| P10-1 | Release hardening | done | `fix/p10-release-hardening` | `4322f03` | `ca1481e` | ruff, format, mypy, pytest (292), coverage 80.64% | signed-manifest test, dev update extra |
| P10-2 | CI repair | done | `fix/ci` | `12049e1` | `b37b12b` | ruff, format, mypy, pytest (292), coverage 80.64% | cross-platform binary update test, wheel smoke venv, coverage margin |
| P11 | MIT relicense | done | `feat/p11-mit-license` | `7ee05d9` | `123d8ee` | ruff, format, mypy (63), pytest (292), coverage 81.64% | MIT LICENSE/NOTICE; license module, CLI, config and EULA removed; active mode unconditional; version `0.4.0`; signed updates retained |
| Audit | History secret scan | done | `main` | — | — | scanned 96 commits / 494 blobs | no real credentials; fake credential fixtures in tests only; no sensitive filenames or binary blobs |
| Release | `v0.3.0-alpha` | removed | — | — | — | — | superseded; GitHub release and tag deleted |
| Release | `v0.4.0` | pending | — | `123d8ee` | — | ruff, format, mypy, pytest (292), coverage 81.64% | MIT release; tag and publish; repository still private |

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
| 2026-10-25 | P2-3 | pass | pass (52 files) | 161 passed | reported, not enforced | `b1de5ec` |
| 2026-10-25 | P3 core | pass | pass (53 files) | 180 passed | reported, not enforced | `67f538c` |
| 2026-10-25 | P2 analysis | pass | pass (53 files) | 189 passed | reported, not enforced | `0959c09` |
| 2026-10-25 | P2-6/P4 | pass | pass (54 files) | 201 passed | reported, not enforced | `399c962` |
| 2026-10-25 | P3-7/8/9 | pass | pass (55 files) | 210 passed | reported, not enforced | `97f7d5f` |
| 2026-10-25 | P4-3/P5 | pass | pass (56 files) | 214 passed | reported, not enforced | recorded at merge |
| 2026-10-25 | P6 | pass | pass (58 files) | 232 passed | reported, not enforced | `6c265cf` |
| 2026-10-25 | P5/P6-4/P7 | pass | pass (63 files) | 252 passed | reported, not enforced | `e63ba16` |
| 2026-10-25 | P8 hardening | pass | pass (63 files) | 266 passed | 79% reported, not enforced | `22814b6` |
| 2026-10-25 | P9 hardening | pass | pass (63 files) | 292 passed | 80.64% enforced (CI) | `3a34064` |
| 2026-10-25 | P9-1 savings | pass | pass (63 files) | 292 passed | 80.64% enforced (CI) | `58410ee` |
| 2026-10-25 | P10 release | pass | pass (64 files) | 292 passed | 80.64% enforced (CI) | `ff54faa` |
| 2026-10-25 | P10-1 hardening | pass | pass (64 files) | 292 passed | 80.64% enforced (CI) | `4322f03` |
| 2026-10-25 | P10-2 CI repair | pass | pass (64 files) | 292 passed | 80.64% enforced (CI) | `12049e1` |
| 2026-10-25 | P11 MIT | pass | pass (63 files) | 292 passed | 81.64% (local + CI gate) | `7ee05d9` |
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
- 2026-10-25 — P3 core: ANSI/progress/whitespace/line-dedupe/smart-truncate/
  duplicate-backref pure transforms, tool eligibility, transform registry,
  active-mode wiring, 400/422 retry-with-original, changed-block blob capture,
  and integration tests for shadow vs active behavior.
- 2026-10-25 — P2-4/5/7/8: prefix-drift detection with seven causes and a
  per-session tracker; explicit/implicit cache baseline simulator; W1 redundant
  re-reads, W2 identical outputs, W3 unbatched fan-out, W4 runaway sessions,
  W5 recurring drift and W6 params drift (all advisory, `est.` tokens).
- 2026-10-25 — P2-6/P4: server-rendered Overview + Waste Opportunities pages,
  summary/requests/waste/recommend admin APIs, in-memory per-session drift and
  waste wiring (W1/W2/W4/W5), recommendation ranking, Anthropic cache_control
  stair-step and OpenAI prompt_cache_key hints.
- 2026-10-25 — P3-7/8/9: session-scoped auto-quarantine on fallback/our-fault
  drift, byte-true batch-anchored `cache_serve` with a bounded session map, and
  the stdio MCP `ctxproxy_expand` server with blob retrieval and head/tail
  truncation.
- 2026-10-25 — P4-3/P5: marker-quality metric (markers + coverage to the last
  client cache marker) exposed in health/last request; read-only dashboard
  pages for Live, Sessions, Requests (list + detail), Transforms, Pricing and
  Settings plus matching JSON APIs. Admin token/CSRF/diff viewer/doctor remain.

- 2026-10-25 — P6: native Gemini `generateContent` and Ollama `/api/chat` /
  `/api/generate` adapters with protocol-native segments, string-leaf tool
  results, SSE/NDJSON usage (`usageMetadata`, `prompt_eval_count` /
  `prompt_eval_cached_count` / `eval_count`), and non-stream JSON usage parsing.
  Added opt-in batch-anchored `stale_result_elision`, W7 churn (opt-in
  old/new heuristics) and W8 schema bloat (default on), plus recommendations.

- 2026-10-25 — P5/P6-4/P7: admin Host/token/CSRF middleware; mutating admin
  APIs (config/reload/mode/purge/pricing/waste status/recommend apply) and
  read APIs (timeseries/drift/transform stats/export/SSE live); persisted
  reports, drift, findings and captures; Overview period/rollups, Live SSE,
  Session detail, Request diff viewer, Transforms toggles/stats, Pricing
  editor, Settings/privacy, Doctor page; stale-elision break-even
  calculator; service install/uninstall;
  wheel/PyInstaller CI; README/privacy/FAQ/architecture/test-report/changelog/
  MIT license.

- 2026-10-25 — P8 hardening: implemented and registered
  `volatile_normalizer`; opt-in `inject_stream_usage`; MCP expand
  logging/counters; moving-window guard; export includes transform reports;
  full `capture_payloads=full` request/response fixtures; DB migration backup
  (schema v2); redacted request headers; per-transform fallback incidents and
  waste-over-time; committed golden corpus and transform invariant property
  tests.

- 2026-10-25 — P9 hardening: recommendation suppression (30-day dismissal),
  per-row pricing editor with JSON fallback, guard auto-re-enable and
  expand-error health, CI coverage gate at 80%, release workflow and release
  checklist; doctor/service helper tests.

- 2026-10-25 — P10 release prep: release packaging, signed self-update
  (`ctxproxy update --check/update`), manifest signer, version 0.3.0, release
  workflow/checklist.

- 2026-10-25 — P11 MIT relicense: MIT `LICENSE`/`NOTICE`; removed the license
  module, CLI, config and EULA; active mode is unconditional; version 0.4.0;
  signed updates remain.

- 2026-10-25 — History audit: scanned 96 commits / 494 text blobs for provider
  keys, tokens, private keys, credential assignments, URLs and sensitive
  filenames. Only fake credential fixtures in tests were found. Removed the
  superseded `v0.3.0-alpha` GitHub release and tag.

## Handoff notes

- `git` is installed at `C:\Program Files\Git\cmd\git.exe` but is not on the
  running OpenCode process PATH. Invoke it by full path until OpenCode restarts.
- The system git config sets `core.autocrlf=true`; this repo overrides it to
  `false` and normalizes via `.gitattributes`.
- `origin` is `git@github.com:ahmed-dev25/ctxproxy.git`; CI runs on `main`.
- No live provider captures exist yet. P1-3 may use documented fixtures with a
  `meta.json` source (ADR 0005); captures replace them when available.
- The repository is still private. Tag `v0.4.0` and publish release assets only
  after the update signing keypair/manifest and fresh-machine checks are ready.
- Run `uv sync --extra dev` after cloning; `uv.lock` is committed.
- Ruff formats Python code blocks inside Markdown. `SPEC.md` is excluded in
  `pyproject.toml`; do not remove that exclusion.
