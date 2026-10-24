# 0003 — Defaults for config keys missing from §7.2

- Status: accepted
- Date: 2026-10-24
- Spec refs: §7.2, §11.2, §12.0.4, §12.12, §12.14, §13.6, §13.7, §14.3

## Context

`SPEC.md` references several settings in prose that `§7.2` never defines. P0-2
cannot validate a config model with dangling references, so each one needs a
value now.

## Decision

Add the keys below with these defaults:

| Section | Key | Default | Spec ref | Rationale |
|---|---|---|---|---|
| `guard` | `auto_reenable` | `0` | §12.14 | Disabled by default: quarantine stays until a human or the CLI re-enables it. Conservative. |
| `guard` | `expand_error_rate` | `0.20` | §12.14 | The prose states 20%; make it tunable. |
| `telemetry` | `max_blob_bytes` | `524288000` | §14.3 | The prose states 500 MB. |
| `transforms.openai_hints` | `inject_stream_usage` | `false` | §11.2 | The spec says do not inject by default because it can confuse clients. |
| `transforms.duplicate_backref` | `include_never_touch` | `true` | §12.0.4 | Matches the eligibility matrix: the earlier copy stays intact. |
| `transforms.cache_serve` | `keep_recent_turns` | `12` | §12.12 | `cache_serve` uses the §12.8 boundary but lacked the parameter; mirror `stale_result_elision`. |
| `waste.schema_bloat` | `enabled` | `true` | §13.6 | Detector is on per the table; it is inert until implemented in P6. |
| `waste.schema_bloat` | `min_session_requests` | `10` | §13.7 | Matches the recommendation trigger. |

Everything else follows `§7.2` verbatim.

## Consequences

- P0-2 can validate the full model and emit a complete default `config.toml`.
- If provider verification (P4) contradicts one of these, only the data file and
  this ADR change, not the config schema.
- `waste.schema_bloat.enabled = true` is a promise about a detector that does not
  exist yet; it is documented as inert so nobody expects findings in P0/P1.
