# 0008 — Signed self-updates and the proprietary license

- Status: accepted
- Date: 2026-10-25
- Spec refs: §21, product release decision

## Context

ctxproxy is sold as a low-cost one-time commercial product. Users need a simple
way to receive updates, but updates must not become an arbitrary code-execution
path. The code is distributed as a Python wheel and optionally as a frozen
one-file binary.

## Decision

- The product is licensed under a short **proprietary commercial license**
  (`LICENSE`, `EULA.md`, `NOTICE`), not an OSI open-source license.
- `ctxproxy update --check` and `ctxproxy update` fetch a small manifest over
  HTTPS, verify an Ed25519 signature and SHA-256, then install the artifact.
- The update public key is configured in `[update].public_key` or
  `CTXPROXY_UPDATE_PUBLIC_KEY`. The private key never enters the repository.
- `--allow-unsigned` is a development-only escape hatch.
- One-time purchases include updates within the same major version; a future
  major version may require a new purchase.
- `--check` is side-effect free. `--dry-run` verifies and reports without
  installing.

## Consequences

- Releases must publish a signed manifest alongside artifacts.
- A paid build should embed the public key and require signatures.
- Users can update with one command without a package index or phone-home.
- The license text is intentionally short; legal review is still recommended
  before public launch.
