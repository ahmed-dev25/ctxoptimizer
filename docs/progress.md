# ctxproxy — Progress

**Last updated:** 2026-10-24
**Milestone:** P0 + P1 — transparent proxy + ground-truth telemetry
**Branch:** `feat/p0-2-config`
**Overall:** 2 / 10 tasks complete

## Resume here

- **Last completed:** P0-2 — Config (awaiting merge).
- **Last merge:** `afdae28` (P0-1)
- **Next task:** P0-3 — Models, logging, ULID (`feat/p0-3-models-logging`)
- **Blocked:** P1-3 — usage parsers (awaiting provider captures, see
  `docs/plan.md` §6)
- **Active branch:** `feat/p0-2-config` — merge to `main` before starting P0-3
- **Read first:** `SPEC.md` -> `docs/plan.md` -> this file -> `AGENTS.md`

## Status board

| ID | Task | Status | Branch | Commits | Merge | Gates | Notes |
|---|---|---|---|---|---|---|---|
| P0-1 | Toolchain + skeleton | done | `feat/p0-1-toolchain` | `c7c34c7` | `afdae28` | ruff, format, mypy, pytest (4) | `uv build` and `ctxproxy --version` verified |
| P0-2 | Config | done | `feat/p0-2-config` | recorded at merge | — | ruff, format, mypy, pytest (22) | default template round-trips to model defaults; wheel ships it |
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
| 2026-10-24 | P0-1 | pass | pass (50 files) | 4 passed | reported, not enforced | `c7c34c7` |
| 2026-10-24 | P0-2 | pass | pass (50 files) | 22 passed | reported, not enforced | recorded at merge |

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
