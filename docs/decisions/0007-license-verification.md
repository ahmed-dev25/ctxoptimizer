# 0007 — Ed25519 license verification, enforcement still off

- Status: accepted
- Date: 2026-10-25
- Spec refs: §19, P7-2
- Supersedes/extends: ADR 0002

## Context

ADR 0002 shipped a licensing stub so active-mode work was not blocked. P7-2 now
requires real offline verification while the product decision about charging
and tier enforcement remains with the owner.

## Decision

- `licensing.py` verifies an offline Ed25519-signed JSON license:
  `{email, tier, issued_at, expires_at|null, features, sig}`.
- The public key is supplied at build time (embedded constant) or via
  `CTXPROXY_LICENSE_PUBLIC_KEY`; the private key is never in the repository.
- `LICENSE_ENFORCEMENT` remains `"off"` in this build, so active mode is never
  blocked and expired/invalid licenses degrade to a status banner, not an error.
- `tools/make_license.py` is the dev-only signer; it is outside the wheel.
- Verification requires the optional `[license]` extra (`pynacl`); without it a
  license is reported invalid with an honest reason, never silently accepted.

## Consequences

- A paid build flips `LICENSE_ENFORCEMENT = "on"`, embeds the public key, and
  gets shadow fallback for invalid/expired licenses.
- No phone-home and no network dependency for verification.
- Until the owner chooses a commercial model, local users keep full active mode.
