# ctxproxy — Progress

**Last updated:** 2026-10-24
**Milestone:** P0 + P1 — transparent proxy + ground-truth telemetry
**Branch:** `main`
**Overall:** 4 / 12 tasks complete (Phase 0 complete)

## Resume here

- **Last completed:** P0-4 — Test infrastructure (`b24a59c`).
- **Last merge:** `b509c9f` (P0-4)
- **Next task:** P1-1 — Routing + ingress (`feat/p1-1-routing`)
- **Blocked:** none — P1-3 is unblocked by the dated provider research in
  `docs/provider-notes.md` (ADR 0005)
- **Active branch:** none — working tree is on `main`
- **Read first:** `SPEC.md` -> `docs/plan.md` -> this file -> `AGENTS.md`

## Status board

| ID | Task | Status | Branch | Commits | Merge | Gates | Notes |
|---|---|---|---|---|---|---|---|
| P0-1 | Toolchain + skeleton | done | `feat/p0-1-toolchain` | `c7c34c7` | `afdae28` | ruff, format, mypy, pytest (4) | `uv build` and `ctxproxy --version` verified |
| P0-2 | Config | done | `feat/p0-2-config` | `116adab` | `c37f4f7` | ruff, format, mypy, pytest (22) | default template round-trips to model defaults; wheel ships it |
| P0-3 | Models, logging, ULID | done | `feat/p0-3-models-logging` | `7428195` | `eea33ec` | ruff, format, mypy, pytest (38) | SEC-2 sanitizer + monotonic stdlib ULID |
| P0-4 | Test infrastructure | done | `feat/p0-4-test-infra` | `b24a59c` | `b509c9f` | ruff, format, mypy, pytest (45) | recording uvicorn fake upstream, SSE replay, golden runner |
| P1-1 | Routing + ingress | todo | — | — | — | — | — |
| P1-7 | Named upstreams + profiles | todo | — | — | — | — | — |
| P1-2 | Proxy core | todo | — | — | — | — | — |
| P1-3 | Usage parsers | todo | — | — | — | — | unblocked; doc-derived fixtures allowed (ADR 0005) |
| P1-8 | Gateway usage quirks | todo | — | — | — | — | DeepSeek/OpenRouter/Gemini/Ollama |
| P1-4 | Pricing | todo | — | — | — | — | provider-reported cost supported |
| P1-5 | Store | todo | — | — | — | — | — |
| P1-6 | CLI | todo | — | — | — | — | — |

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
