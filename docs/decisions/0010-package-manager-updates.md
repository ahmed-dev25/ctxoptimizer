# 0010 — Updates through package managers

- Status: accepted
- Date: 2026-10-25
- Supersedes: 0008
- Spec refs: §21

## Context

ctxproxy is free and MIT-licensed. Shipping a built-in self-updater creates a
second remote-code-execution path and requires long-lived release signing keys,
manifest generation, key rotation and code-signing operations. Most users
already install via `uv tool` or `pipx`, both of which provide an upgrade
command.

## Decision

- Remove `ctxproxy update` and the `ctxproxy/update.py` module.
- Remove the `[update]` configuration section, environment overrides, PyNaCl
  extra, manifest schema and `tools/make_update_manifest.py`.
- Document upgrades with `uv tool upgrade ctxproxy` or
  `pipx upgrade ctxproxy`.
- Publish wheels, sdists and `SHA256SUMS`; PyInstaller binaries remained
  unsigned until ADR 0011 removed them from the distribution.
- Trust for package installs comes from the package index/GitHub release channel
  and TLS. There is no phone-home update check.

## Consequences

- No signing keypair or manifest lifecycle is required for the free release.
- ctxproxy no longer downloads and executes update artifacts itself.
- Users must update through their package manager; there is no in-app update
  prompt.
- Package-index account security and GitHub release permissions become the
  primary update trust boundary.
- ADR 0011 later removes standalone binaries and OS code-signing entirely.
