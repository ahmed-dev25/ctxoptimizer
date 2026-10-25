# 0001 — Toolchain, Python floor and git flow

- Status: accepted
- Date: 2026-10-24
- Spec refs: §6, §20.2, §21, §24.1

## Context

`SPEC.md` targets Python >= 3.11 with a 3.11/3.12/3.13 CI matrix and hatchling.
The repository scaffold already used `uv_build` and Python 3.14, and the machine
runs Python 3.14.7 with uv 0.13.1. The system-wide git config sets
`core.autocrlf=true`, which would rewrite CRLF in captured SSE fixtures.

## Decision

1. Keep `uv_build` and the src layout; set the entry point to
   `ctxoptimizer.cli:app`.
2. `requires-python = ">=3.11"`; develop on 3.14; CI tests 3.11 and 3.14 (the
   two ends of the supported range) on Linux, macOS and Windows.
3. Set repo-local `core.autocrlf=false` and normalize via `.gitattributes`:
   `* text=auto eol=lf`, with `tests/fixtures/** -text` so captures stay
   byte-identical.
4. Commit the CI workflow now; it stays dormant until a remote exists.
5. Repo-local identity is `ahmed` / `ahmed.devv25@gmail.com` (does not touch the
   global config, which uses `ahmed_dev`).
6. One branch per task (`feat/<id>-<slug>`), merge with `--no-ff`, delete the
   branch and leave the tree on `main`.
7. Report coverage from the first task but enforce it only on implemented
   modules. `pip-audit` is non-blocking until packaging.

## Consequences

- Code must remain 3.11-compatible: no 3.12+ syntax, even though dev runs 3.14.
- Python 3.12 and 3.13 are not gated; the risk is low because they sit between
  two tested versions.
- Fixtures survive checkout unchanged, which is required to test CRLF and SSE
  framing behavior honestly.
- Until a remote is configured, regression detection is manual through the
  local gate commands.
