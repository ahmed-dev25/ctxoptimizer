# 0008 — Signed self-updates

- Status: superseded by 0010
- Date: 2026-10-25
- Spec refs: §21

## Context

Users need a simple way to receive updates without a package index or manual
downloads. Updates must not become an arbitrary code-execution path. The code is
distributed as a Python wheel and optionally as a frozen one-file binary.

## Decision

- `ctxproxy update --check` and `ctxproxy update` fetch a small manifest over
  HTTPS, verify an Ed25519 signature and SHA-256, then install the artifact.
- The update public key is configured in `[update].public_key` or
  `CTXPROXY_UPDATE_PUBLIC_KEY`. The private key never enters the repository.
- `--allow-unsigned` is a development-only escape hatch.
- `--check` is side-effect free. `--dry-run` verifies and reports without
  installing.
- This is a security feature, not a licensing or payment mechanism.

## Consequences

- Releases must publish a signed manifest alongside artifacts.
- Users can update with one command without a phone-home.
- The optional `[update]` extra installs `pynacl` for signature verification.
