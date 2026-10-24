# 0002 — Licensing module is a stub in v1

- Status: accepted
- Date: 2026-10-24
- Spec refs: §19, §1.4

## Context

`SPEC.md` suggests a commercial split: free tier = passthrough + shadow,
paid = active mode and all transforms. Enforcing that from the first line of
code would add license fixtures and a bypass build flag to every active-mode
test, while no active-mode code exists in P0/P1.

## Decision

Ship `ctxproxy/licensing.py` as an isolated stub:

- `is_active_mode_allowed() -> bool` returns `True`.
- `license_status()` returns a constant "unlicensed, enforcement off" status.
- A `LICENSE_ENFORCEMENT` build flag exists and defaults to `off`.
- Nothing outside `licensing.py` imports its internals.

## Consequences

- Active mode will not be blocked in tests or local use.
- The P7 work item still owns real Ed25519 verification, tiers and grace
  behavior; the public surface is already in place.
- Turning enforcement on later is a single flag plus a config path, not a
  refactor of the proxy.
