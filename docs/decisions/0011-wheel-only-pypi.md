# 0011 — Wheel-only distribution on PyPI

- Status: accepted
- Date: 2026-10-25
- Spec refs: §21

## Context

Standalone PyInstaller binaries require Windows Authenticode certificates and
Apple Developer ID signing/notarization. Both require identity verification,
paid accounts and ongoing credential management. The Python package also saw
the majority of install friction, while `uv tool` and `pipx` already provide
clean install/upgrade flows.

## Decision

- Distribute wheel and sdist only.
- Publish to PyPI with GitHub Actions Trusted Publishing (OIDC), not a stored
  token.
- Generate PEP 740 attestations for uploaded distributions and GitHub build
  provenance for release artifacts.
- Keep GitHub releases for wheel/sdist and `SHA256SUMS`.
- Remove PyInstaller builds, standalone binaries, OS code-signing/notarization
  steps and the associated documentation.
- Keep `uv tool upgrade ctxproxy` / `pipx upgrade ctxproxy` as the update path.

## Consequences

- No Windows or macOS signing certificates are needed.
- Users need Python 3.11+; there is no zero-Python download.
- PyPI project ownership and the GitHub trusted-publisher configuration become
  the release trust boundary.
- The package name must be owned on PyPI before publishing.
- Binary SmartScreen/Gatekeeper warnings disappear because no binaries are
  distributed.
