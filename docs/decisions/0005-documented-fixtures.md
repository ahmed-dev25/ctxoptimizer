# 0005 — Documented-shape fixtures are allowed when sourced and dated

- Status: accepted
- Date: 2026-10-24
- Supersedes: part of ADR 0004 (the "captures only" gate for P1-3)
- Spec refs: §0.4, §14.1, §20.1

## Context

ADR 0004 required provider captures before P1-3 could start. On 2026-10-24 the
wire formats and usage objects for Anthropic Messages, OpenAI Chat Completions
and OpenAI Responses were resolved from current official documentation and the
official Python SDK type definitions, and recorded with sources and access dates
in `docs/provider-notes.md`.

No captures exist yet. Keeping P1-3 blocked would delay the milestone without
improving correctness, because the documented shapes are now primary-source
material rather than guesses.

## Decision

1. Official documentation and official SDK type definitions are a valid source
   for parser implementation, provided each finding is recorded in
   `docs/provider-notes.md` with a URL and access date.
2. Fixtures may be derived from those documented shapes. Each case must carry a
   `meta.json` with:
   - `"source": "documented"`,
   - the source URL(s),
   - the access date (`2026-10-24`),
   - a note describing what the fixture exercises.
3. Documented fixtures must reproduce the documented framing byte-for-byte:
   `event:` lines where the provider sends them, CRLF/LF variants where they
   matter, and `[DONE]` only where the provider sends it.
4. A documented fixture is never labelled a capture. Real captures remain the
   preferred validation, and replace a documented fixture when they arrive.
5. Everything else in ADR 0004 still applies to captures: raw bytes,
   `tests/fixtures/** -text`, sanitization, and `meta.json`.

## Consequences

- P1-3 is unblocked: parsers and tests can be written now.
- Residual risk is documentation drift or a transcription error in a fixture.
  Live captures (`pytest -m live`) remain the final check and are recorded in
  `docs/provider-notes.md` when available.
- Future provider work (Gemini, Ollama) follows the same rule: document first,
  fixture second, capture when possible.
