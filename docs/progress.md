# ctxproxy — Progress

**Last updated:** 2026-10-24
**Milestone:** P0 + P1 — transparent proxy + ground-truth telemetry
**Branch:** `feat/p0-1-toolchain`
**Overall:** 1 / 10 tasks complete

## Resume here

- **Last completed:** P0-1 — Toolchain + skeleton (awaiting merge).
- **Last merge:** —
- **Next task:** P0-2 — Config (`feat/p0-2-config`)
- **Blocked:** P1-3 — usage parsers (awaiting provider captures, see
  `docs/plan.md` §6)
- **Active branch:** `feat/p0-1-toolchain` — merge to `main` before starting P0-2
- **Read first:** `SPEC.md` -> `docs/plan.md` -> this file -> `AGENTS.md`

## Status board

| ID | Task | Status | Branch | Commits | Merge | Gates | Notes |
|---|---|---|---|---|---|---|---|
| P0-1 | Toolchain + skeleton | done | `feat/p0-1-toolchain` | recorded at merge | — | ruff, format, mypy, pytest (4) | `uv build` and `ctxproxy --version` verified |
| P0-2 | Config | todo | — | — | — | — | — |
| P0-3 | Models, logging, ULID | todo | — | — | — | — | — |
| P0-4 | Test infrastructure | todo | — | — | — | — | — |
| P1-1 | Routing + ingress | todo | — | — | — | — | — |
| P1-2 | Proxy core | todo | — | — | — | — | — |
| P1-4 | Pricing | todo | — | — | — | — | — |
| P1-5 | Store | todo | — | — | — | — | — |
| P1-6 | CLI | todo | — | — | — | — | — |
| P1-3 | Usage parsers | blocked | — | — | — | — | waiting on captures |

Status vocabulary: `todo` -> `in-progress` -> `blocked` -> `review` -> `done`.
Rows are in execution order; see `docs/plan.md` §4.

## Gate log

| Date | Task | ruff | mypy | pytest | coverage | Commit |
|---|---|---|---|---|---|---|
| 2026-10-24 | bootstrap | n/a (docs only) | n/a | n/a | n/a | `5b3f61b` |
| 2026-10-24 | P0-1 | pass | pass (50 files) | 4 passed | reported, not enforced | recorded at merge |

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

## Handoff notes

- `git` is installed at `C:\Program Files\Git\cmd\git.exe` but is not on the
  running OpenCode process PATH. Invoke it by full path until OpenCode restarts.
- The system git config sets `core.autocrlf=true`; this repo overrides it to
  `false` and normalizes via `.gitattributes`.
- No remote is configured yet, so `.github/workflows/ci.yml` is dormant.
- No provider captures exist yet; P1-3 stays blocked and P1-2 ships a null parser.
- Run `uv sync --extra dev` after cloning; `uv.lock` is committed.
- Ruff formats Python code blocks inside Markdown. `SPEC.md` is excluded in
  `pyproject.toml`; do not remove that exclusion.
