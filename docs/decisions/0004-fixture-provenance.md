# 0004 — Provider fixtures come from real captures

- Status: accepted
- Date: 2026-10-24
- Spec refs: §0.4, §14.1, §20.1, §20.3

## Context

`SPEC.md` forbids inventing provider API behavior: anything marked VERIFY must be
checked against current docs or real traffic. The usage parsers (P1-3) are
exactly that kind of code, and a hand-written SSE fixture would encode our
reading of the spec rather than what providers actually send.

## Decision

1. P1-3 parser tests run against raw captures supplied by the repository owner,
   stored under `tests/fixtures/<provider>/` and marked `-text` in
   `.gitattributes`.
2. Required captures and their purpose are listed in `docs/plan.md` §6.
3. Every provider folder carries a `meta.json` with capture date, client, model
   and a sanitization confirmation. Prompts and secrets are removed before
   committing.
4. No hand-written fixture is presented as real. Until a provider's captures
   exist, the proxy uses the null usage parser and records
   `usage_source="none"`; the dashboard and `doctor` report the gap honestly.
5. `docs/provider-notes.md` records dated findings from official documentation
   and from each captured sample.

## Consequences

- P1-3 is blocked until captures arrive; the rest of P1 is unaffected.
- Parser behavior is verified against reality, not against assumptions.
- A provider with no captures still works, but its cost figures are visibly
  incomplete rather than silently wrong (INV-13).
