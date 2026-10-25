# Agent instructions

ctxoptimizer is a local LLM cost-optimization proxy. `SPEC.md` is authoritative.
Read, in this order: `SPEC.md`, `docs/plan.md`, `docs/progress.md`, `AGENTS.md`.

## Hard rules

- Invariants INV-1..INV-18 (`SPEC.md` §2) are non-negotiable.
- Implement only the task named in `docs/progress.md` as the next task. Never
  start a later phase.
- Tests first or alongside. A task is not done until every gate passes.
- Never read, print, or commit API keys or captured credentials. Use fake keys
  in tests.
- Do not guess provider behavior marked VERIFY; use real captures or record the
  assumption in `docs/provider-notes.md`.
- No new dependencies outside `SPEC.md` §6 and `pyproject.toml`.
- Keep modules under ~300 lines.
- On ambiguity choose the most conservative behavior (forward the request
  unchanged) and state the assumption in the final report.

## Gates (all must pass before a commit)

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy --strict src
uv run pytest -q
```

## Git workflow

- Identity is repo-local: `user.name=ahmed`, `user.email=ahmed.devv25@gmail.com`.
- `main` is the only long-lived branch. Do not commit directly to `main` except
  for the bootstrap commit and per-task `chore(progress)` metadata commits.
- One task = one branch: `feat/<task-id>-<slug>` (for example
  `feat/p0-1-toolchain`).
- Use Conventional Commits with the task id: `feat(p0-1): ...`.
- Merge with `--no-ff`, delete the branch, and leave the working tree on `main`.
- Update `docs/progress.md` on the task branch before merging: status, branch,
  commit SHAs, gate results and changelog.
- After merging, add one `chore(progress): record merge for <task>` commit on
  `main` that fills in the merge SHA.

## Reporting format

Final message: (1) what changed, (2) tests added, (3) assumptions, (4) follow-ups
and risks.
