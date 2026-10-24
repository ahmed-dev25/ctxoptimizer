# Architecture Decision Records

Short, dated records of decisions that deviate from or clarify `SPEC.md`. One
file per decision, numbered sequentially. Append-only: supersede an ADR with a
new one rather than rewriting history.

## Index

| ADR | Title | Status | Date |
|---|---|---|---|
| [0001](0001-toolchain.md) | Toolchain, Python floor and git flow | accepted | 2026-10-24 |
| [0002](0002-licensing-stub.md) | Licensing module is a stub in v1 | accepted | 2026-10-24 |
| [0003](0003-config-gap-defaults.md) | Defaults for config keys missing from §7.2 | accepted | 2026-10-24 |
| [0004](0004-fixture-provenance.md) | Provider fixtures come from real captures | accepted | 2026-10-24 |
| [0005](0005-documented-fixtures.md) | Documented-shape fixtures are allowed when sourced | accepted | 2026-10-24 |
| [0006](0006-provider-profiles.md) | Protocol-first support with named upstreams and profiles | accepted | 2026-10-24 |

## Template

```md
# NNNN — Title

- Status: proposed | accepted | superseded by NNNN
- Date: YYYY-MM-DD
- Spec refs: §…

## Context
What forced a decision.

## Decision
What we chose, in one list.

## Consequences
What becomes easier, what becomes harder, what is now untested.
```
