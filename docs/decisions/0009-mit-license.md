# 0009 — MIT open-source license

- Status: accepted
- Date: 2026-10-25
- Replaces: the earlier proprietary-license decision

## Context

ctxproxy is a small local developer tool in a crowded market. The goal is
adoption, sharing and community value, not selling the core binary. A
proprietary license added friction without a realistic revenue path.

## Decision

- ctxproxy is licensed under the **MIT License**.
- `LICENSE` is the canonical license; `NOTICE` covers attribution and provider
  trademarks.
- The paid-license module, activation checks, license CLI, license config and
  EULA are removed.
- Signed self-updates remained at the time; ADR 0010 later removed the built-in
  updater in favour of package-manager upgrades.
- The repository is intended to be public; the source link is included in the
  README and website.

## Consequences

- Anyone may use, modify, redistribute or sell the software under MIT.
- There is no paid active-mode gate; active mode is always available.
- A future hosted/team product must be a separate service or repository.
- Prior private releases under the old license are not affected; the MIT
  license starts with the next release (`v0.4.0`).
