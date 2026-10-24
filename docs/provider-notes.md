# Provider notes — usage parsing (P1-3)

**Researched:** 2026-10-24
**Method:** current official provider documentation plus the official Python SDK
type definitions (primary sources). No live traffic captured yet.
**Scope:** Anthropic Messages, OpenAI Chat Completions, OpenAI Responses,
native Gemini `generateContent`, native Ollama `/api/chat` and `/api/generate`.
**Rule:** only documented behavior is recorded below, each with a source and an
access date. Anything absent is unknown and must not be guessed (SPEC §0.4).

---

## 1. Cross-cutting SSE rules

All three APIs stream Server-Sent Events over `text/event-stream`.

Wire grammar (WHATWG HTML §9.2.6, referenced by the OpenAI SDK decoder):

- Lines end with CRLF, LF, or CR.
- An event is dispatched on a blank line.
- `field: value`; one optional space after the colon is stripped.
- `data:` lines accumulate and are joined with `\n`.
- Lines starting with `:` are comments and are ignored.
- `event:`, `id:`, `retry:` are fields; unknown fields are ignored.
- A single leading UTF-8 BOM may appear at the start of the stream.

Parsing requirements that follow:

1. Buffer **bytes** and split on complete lines; only then decode UTF-8. A chunk
   can split a multi-byte character, so decoding chunks directly loses text.
2. Join multiple `data:` lines with `\n` before JSON parsing.
3. Ignore comments, `ping`-style keepalives, unknown fields and unknown event
   types. New event types may be added (Anthropic states this explicitly).
4. Bound the line and event buffers (suggest 4 MiB line / 8 MiB event). On
   overflow, disable usage parsing for the request; never raise into the
   forwarding path (INV-1, INV-3).
5. Decode with `errors="replace"` or catch decoding failures and ignore the
   event. A malformed stream must degrade to `usage_source="none"`, not break
   the response.
6. Treat EOF as end of stream. `data: [DONE]` is a terminator when present; it
   is not guaranteed by every endpoint.

Sources:
- https://html.spec.whatwg.org/multipage/server-sent-events.html
- https://raw.githubusercontent.com/openai/openai-python/main/src/openai/_streaming.py
  (reference decoder: line splitting, comments, `[DONE]`, field parsing)

---

## 2. Anthropic Messages (`POST /v1/messages`)

### 2.1 Streaming event sequence

1. `message_start` — a `Message` object with empty `content` and a `usage` object.
2. Per content block: `content_block_start`, zero or more `content_block_delta`,
   `content_block_stop`.
3. One or more `message_delta` events — top-level changes (`stop_reason`) and
   usage.
4. `message_stop`.
5. `ping` events may appear anywhere; `error` events may appear mid-stream.

Each event carries both an SSE `event:` name and a matching `type` field in the
JSON data. Example:

```
event: message_start
data: {"type":"message_start","message":{"id":"msg_...","type":"message","role":"assistant","content":[],"usage":{"input_tokens":2679,"cache_creation_input_tokens":0,"cache_read_input_tokens":0,"output_tokens":3}}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello"}}

event: message_delta
data: {"type":"message_delta","delta":{"stop_reason":"end_turn","stop_sequence":null},"usage":{"input_tokens":10682,"cache_creation_input_tokens":0,"cache_read_input_tokens":0,"output_tokens":510}}

event: message_stop
data: {"type":"message_stop"}
```

### 2.2 Usage objects

`message_start.message.usage` is the full `Usage` object:

| Field | Type | Meaning |
|---|---|---|
| `input_tokens` | int (required) | Input tokens **after the last cache breakpoint**; excludes cache reads/writes |
| `cache_creation_input_tokens` | int? | Tokens written to cache (total) |
| `cache_read_input_tokens` | int? | Tokens read from cache |
| `cache_creation` | object? | Breakdown: `ephemeral_5m_input_tokens`, `ephemeral_1h_input_tokens` (both required inside the object) |
| `output_tokens` | int (required) | Output tokens, including thinking |
| `output_tokens_details` | object? | `thinking_tokens` (int) — reasoning subset, always <= `output_tokens` |
| `server_tool_use` | object? | e.g. `web_search_requests` |
| `service_tier` | string? | `standard` / `priority` / `batch` |
| `speed` | string? | `standard` / `fast` |
| `inference_geo` | string? | Region |

`message_delta.usage` is `MessageDeltaUsage`:

| Field | Type | Meaning |
|---|---|---|
| `output_tokens` | int (required) | **Cumulative** output tokens |
| `input_tokens` | int? | **Cumulative**; may repeat message_start |
| `cache_creation_input_tokens` | int? | **Cumulative** |
| `cache_read_input_tokens` | int? | **Cumulative** |
| `output_tokens_details` | object? | Same thinking breakdown |
| `server_tool_use` | object? | Cumulative counters |

Key facts:

- **All counts in `message_delta` are cumulative, not per-chunk.** Do not sum
  events. Take the **last non-null value** for each field.
- `message_delta` has **no** `cache_creation` TTL breakdown. Only the
  `message_start` `Usage` object (and the non-streaming response) carries it.
- `message_start` may omit the cache fields entirely when caching was not used.
- The docs example shows `input_tokens` growing from 2,679 at `message_start` to
  10,682 at `message_delta` during a server-tool turn. Taking the final value is
  mandatory.
- Non-streaming responses carry the same `Usage` object as
  `response.usage`.

### 2.3 Normalization (SPEC §14.1)

```
fresh_input      = input_tokens
cache_read       = cache_read_input_tokens or 0
cache_write_5m   = cache_creation.ephemeral_5m_input_tokens
cache_write_1h   = cache_creation.ephemeral_1h_input_tokens
                   else: cache_creation_input_tokens goes entirely to 5m
output           = output_tokens
reasoning        = output_tokens_details.thinking_tokens (subset of output)
source           = "provider"
```

Do not add `reasoning` to `output` for cost. Total input is
`fresh_input + cache_read + cache_write_5m + cache_write_1h`, which matches the
documented identity `read + creation + input`.

If `cache_creation` is present but only one TTL bucket is non-zero, use those
values. If the breakdown is absent and `cache_creation_input_tokens > 0`, the
SPEC rule (treat it as 5m) is the conservative fallback; flag the request in
telemetry notes so a mispriced 1h-only write is visible.

### 2.4 Cache facts that affect parsing and pricing (resolves SPEC §26.1)

- Cache prefix order: `tools` -> `system` -> `messages`.
- Max 4 breakpoints per request.
- Lookback window: 20 blocks; consecutive `tool_use` or `tool_result` blocks
  count as one position.
- TTLs: `5m` (default) and `1h`.
- `input_tokens` means tokens after the last breakpoint, not all input.
- Automatic caching: a top-level `cache_control: {"type":"ephemeral"}` is now
  supported and moves the breakpoint to the last cacheable block. Combining it
  with 4 explicit breakpoints is a 400; mixing TTLs on the same block is a 400.
- Minimum cacheable prefix length by model (documented 2026-10-24):
  - 512: Claude Fable 5.1, Mythos 5.1, Opus 5.5, Opus 5, Sonnet 5.5, Fable 5,
    Mythos 5, Haiku 5.5
  - 1,024: Opus 4.8, Sonnet 5, Sonnet 4.6, Sonnet 4.5, Opus 4.1, Opus 4,
    Sonnet 4
  - 2,048: Mythos Preview, Opus 4.7, Haiku 3.5
  - 4,096: Opus 4.6, Opus 4.5, Haiku 4.5
- Write multipliers: 5m = 1.25x base input, 1h = 2x base input.
- Read multiplier: 0.1x standard; 0.05x on Opus 5.5 and Sonnet 5.5; 0.025x on
  Fable 5.1 and Mythos 5.1.
- Per-model absolute prices are published in the caching pricing table; use
  them for `pricing.json`, not derived multipliers where both exist.

Sources:
- https://platform.claude.com/docs/en/build-with-claude/streaming
- https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- https://platform.claude.com/docs/en/api/messages
- https://raw.githubusercontent.com/anthropics/anthropic-sdk-python/main/src/anthropic/types/usage.py
- https://raw.githubusercontent.com/anthropics/anthropic-sdk-python/main/src/anthropic/types/message_delta_usage.py
- https://raw.githubusercontent.com/anthropics/anthropic-sdk-python/main/src/anthropic/types/cache_creation.py
- https://raw.githubusercontent.com/anthropics/anthropic-sdk-python/main/src/anthropic/types/output_tokens_details.py

---

## 3. OpenAI Chat Completions (`POST /v1/chat/completions`)

### 3.1 Wire format

- Each event is a single `data: <json>` line followed by a blank line.
- The stream conventionally ends with `data: [DONE]`. This is not in the formal
  API reference but is de facto wire behavior and the official SDK handles it.
- Chat Completions does **not** send `event:` names.
- EOF without `[DONE]` must be treated as a terminated stream.

### 3.2 Usage chunk

- Usage is present only when the request set
  `stream_options: {"include_usage": true}`.
- When enabled, every chunk carries `usage: null` except the **final** chunk,
  which carries the totals and may have `choices: []`.
- If the stream is interrupted or cancelled, that final chunk may never arrive.
- `usage` can therefore be detected independently of `choices`.

`CompletionUsage`:

| Field | Type | Meaning |
|---|---|---|
| `prompt_tokens` | int (required) | Includes cached and cache-write tokens |
| `completion_tokens` | int (required) | Includes reasoning and prediction tokens |
| `total_tokens` | int (required) | prompt + completion |
| `prompt_tokens_details.cached_tokens` | int? | Cache reads |
| `prompt_tokens_details.cache_write_tokens` | int? | Tokens written to cache (new) |
| `prompt_tokens_details.audio_tokens` | int? | Audio input |
| `prompt_tokens_details.image_tokens` | int? | Image input |
| `prompt_tokens_details.text_tokens` | int? | Text input |
| `completion_tokens_details.reasoning_tokens` | int? | Reasoning subset |
| `completion_tokens_details.accepted_prediction_tokens` | int? | Predicted outputs |
| `completion_tokens_details.rejected_prediction_tokens` | int? | Predicted outputs |
| `completion_tokens_details.audio_tokens` | int? | Audio output |
| `completion_tokens_details.text_tokens` | int? | Text output |

### 3.3 Normalization

```
fresh_input = max(prompt_tokens - cached_tokens - cache_write_tokens, 0)
cache_read  = cached_tokens or 0
cache_write = cache_write_tokens or 0
output      = completion_tokens
reasoning   = completion_tokens_details.reasoning_tokens (subset of output)
source      = "provider"
```

**SPEC correction:** §11.2/§14.1 say `fresh_input = prompt_tokens -
cached_tokens`. That is now wrong: `prompt_tokens` includes cache-write tokens
as well. See §5.

If `include_usage` is absent, the parser falls back to `source="estimated"`:
count output characters from `choices[].delta.content` (and reasoning deltas if
visible) and apply the §12.0.2 estimator. The caller fills the input estimate
from the request payload.

### 3.4 Cache facts (resolves SPEC §26.2)

- Prompt caching is enabled by default for supported models.
- Minimum cacheable prefix: 1,024 visible input tokens for GPT-5.6 and later;
  earlier models vary by request settings.
- GPT-5.6 and later: cache writes cost 1.25x ordinary input for a 30-minute
  minimum lifetime, or 2.5x for 12 hours in the Responses API. Reads cost 0.1x
  (0.05x on GPT-6.1 Sol).
- GPT-5.5 and earlier: no separate cache-write charge; implicit caching only;
  `prompt_cache_retention` is `in_memory` (about 5-10 minutes) or `24h`.
- `prompt_cache_key` influences routing (and separates accounting). On GPT-5.6+
  routing is automatic and the key is optional; on earlier models it matters.
- `prompt_cache_options.mode` (`implicit`/`explicit`), `prompt_cache_breakpoint`,
  and `prompt_cache_options.ttl` (`30m`/`12h`) are GPT-5.6+ Responses features.
  Chat Completions exposes only `prompt_cache_key` and, on older models,
  `prompt_cache_retention`.

Sources:
- https://developers.openai.com/api/reference/resources/chat/subresources/completions/streaming-events/
- https://developers.openai.com/api/docs/guides/prompt-caching
- https://raw.githubusercontent.com/openai/openai-python/main/src/openai/types/completion_usage.py
- https://raw.githubusercontent.com/openai/openai-python/main/src/openai/types/chat/chat_completion_chunk.py

---

## 4. OpenAI Responses (`POST /v1/responses`)

### 4.1 Wire format

- Events are semantic and typed: `event: <type>` plus `data: <json>`.
- Event names include `response.created`, `response.in_progress`,
  `response.output_item.added`, `response.output_text.delta`,
  `response.function_call_arguments.delta`, `response.completed`,
  `response.incomplete`, `response.failed`, and `error`.
- No `[DONE]` sentinel is documented for Responses. Tolerate one if present,
  but rely on `response.completed`/`response.incomplete` or EOF.
- `response.created` contains a `Response` object whose `usage` is null; it is
  not the final usage.

### 4.2 Usage location

True usage is carried on the final `Response` object:

```
event: response.completed
data: {"type":"response.completed","sequence_number":42,"response":{"id":"resp_...","status":"completed","usage":{"input_tokens":12000,"input_tokens_details":{"cached_tokens":4000,"cache_write_tokens":7000},"output_tokens":900,"output_tokens_details":{"reasoning_tokens":300},"total_tokens":12900}}}
```

`ResponseUsage`:

| Field | Type | Meaning |
|---|---|---|
| `input_tokens` | int (required) | Includes cached and cache-write tokens |
| `input_tokens_details.cached_tokens` | int (required in SDK) | Cache reads |
| `input_tokens_details.cache_write_tokens` | int (required in SDK) | Tokens written to cache |
| `input_tokens_details.cache_write_tokens_details.ttl_30m_tokens` | int? | Documented TTL split (not yet in the SDK type) |
| `input_tokens_details.cache_write_tokens_details.ttl_12h_tokens` | int? | Documented TTL split |
| `output_tokens` | int (required) | Includes reasoning |
| `output_tokens_details.reasoning_tokens` | int (required in SDK) | Reasoning subset |
| `total_tokens` | int (required) | input + output |

Defensive parsing: treat the details objects as optional, because older models
or gateways may omit them even though the SDK marks them required.

### 4.3 Normalization

```
fresh_input = max(input_tokens - cached_tokens - cache_write_tokens, 0)
cache_read  = cached_tokens or 0
cache_write_30m = ttl_30m_tokens
cache_write_12h = ttl_12h_tokens
                  else: cache_write_tokens goes to an "unknown TTL" bucket
output      = output_tokens
reasoning   = output_tokens_details.reasoning_tokens
source      = "provider"
```

Parse usage from `response.completed` **and** `response.incomplete` (a truncated
response still bills). If `response.failed`/`error` arrives without usage, keep
`source="none"` unless an earlier event supplied usage.

`previous_response_id` does not change the usage shape; the final Response still
carries `usage`. There is no payload to compact when the server holds state
(SPEC §11.3), which is a P2 concern, not a parser concern.

Sources:
- https://developers.openai.com/api/docs/guides/streaming-responses
- https://developers.openai.com/api/reference/resources/responses/streaming-events/
- https://developers.openai.com/api/docs/guides/prompt-caching
- https://raw.githubusercontent.com/openai/openai-python/main/src/openai/types/responses/response_usage.py
- https://raw.githubusercontent.com/openai/openai-python/main/src/openai/types/responses/response_completed_event.py

---

## 5. Impact on SPEC.md (deviations to record before coding)

| SPEC location | Current assumption | Documented reality (2026-10-24) | Action |
|---|---|---|---|
| §11.2, §14.1 | OpenAI `fresh_input = prompt_tokens - cached_tokens` | `prompt_tokens` also includes `cache_write_tokens` | Subtract both; clamp at 0 |
| §14.1 | Anthropic `reasoning` is n/a | `usage.output_tokens_details.thinking_tokens` exists | Map it to `Usage.reasoning`; never add to output cost |
| §10 `Usage` | Only `cache_write_5m` / `cache_write_1h` | OpenAI writes have `ttl_30m` / `ttl_12h` buckets | Add `cache_write_30m` / `cache_write_12h` (or a generic TTL map) |
| §14.2 `pricing.json` | No OpenAI cache-write rates | GPT-5.6+: 1.25x (30m) / 2.5x (12h); reads 0.1x (0.05x GPT-6.1 Sol) | Add write-rate fields per model in P1-4 |
| §13.5 baseline simulator | "OpenAI: no write fees" | False for GPT-5.6+ | Update simulator in P2-5 |
| §12.9 `anthropic_cache` | Per-model minimums "e.g. 1024/2048/4096" | Exact per-model list now documented; top-level automatic caching exists | Fill `cache_limits.json` and revisit strategy in P4 |
| §12.10 `openai_hints` | `prompt_cache_key` is the main lever | GPT-5.6+ routes automatically; explicit breakpoints and TTLs exist | Re-verify and likely redesign in P4 |
| §26.1–§26.3 | Open questions | Resolved for Anthropic/OpenAI by this document | Keep Gemini open for P6 |

These do not block P1-3's structure: the parser can emit the new fields, and
pricing/baseline changes land in P1-4/P2-5.

---

## 6. P1-3 implementation decisions

1. **One byte-level SSE decoder** shared by all providers, written to the WHATWG
   grammar above. Provider parsers only consume `(event_name, data_json)`.
2. **Parser protocol** (in `telemetry/usage.py`):
   `feed(chunk: bytes) -> None`, `disable() -> None`, `result() -> Usage`.
   `feed` never raises; any internal error disables the parser and preserves
   whatever was parsed so far.
3. **Anthropic parser**: on `message_start` capture the full `Usage`; on
   `message_delta` overwrite each present field (cumulative => last wins); ignore
   `ping`/unknown; on `event: error` keep partial values and mark the outcome.
4. **Chat parser**: ignore chunks with `usage: null`; accept the usage chunk
   regardless of `choices`; stop at `[DONE]`; accumulate output characters for
   the estimated fallback.
5. **Responses parser**: only read usage from `response.completed` and
   `response.incomplete`; ignore `response.created`; tolerate missing detail
   objects; stop at EOF or `[DONE]`.
6. **Non-stream parsers**: parse `usage` from the JSON body for all three
   providers; return `Usage` with `source="provider"` or `"none"`.
7. **Null parser** for unknown endpoints/providers: `source="none"`, no state.
8. **Estimated fallback**: when a stream ends without usage, set
   `source="estimated"` and estimate output tokens from accumulated output
   characters with the §12.0.2 estimator; the proxy finalizer fills the input
   estimate from the request.
9. **Memory**: cap the SSE line buffer and event buffer; on overflow call
   `disable()` and record `usage_source="none"`. No exceptions cross the
   forwarding boundary (INV-3).

---

## 7. Fixtures and provenance

Official documentation is now sufficient to define the wire shapes. Fixtures
derived from these documented shapes are allowed when they are:

- stored as raw bytes under `tests/fixtures/<provider>/`,
- tagged in `meta.json` with `source: "documented"`, the source URL, the access
  date (`2026-10-24`), and the provider SDK/doc version,
- reviewed for byte fidelity (CRLF, `event:` lines, `[DONE]`).

Real captures remain the preferred validation and supersede a documented
fixture when available. See ADR 0005.

Required fixture set (same paths as `docs/plan.md` §6):

```
tests/fixtures/anthropic/messages_stream.sse
tests/fixtures/anthropic/messages_stream_cached.sse
tests/fixtures/anthropic/messages.json
tests/fixtures/openai/chat_stream_usage.sse
tests/fixtures/openai/chat_stream_no_usage.sse
tests/fixtures/openai/chat.json
tests/fixtures/openai/responses_stream.sse
tests/fixtures/openai/responses.json
```

---

## 8. Remaining unknowns (live capture will settle these)

- Whether OpenAI Responses ever emits `data: [DONE]` in practice (not
  documented; parser tolerates either).
- Whether Anthropic always includes cache fields in `message_start` or only when
  caching was requested (type marks them optional; parser handles absence).
- Availability and exact shape of
  `input_tokens_details.cache_write_tokens_details` in Chat Completions (the
  Responses guide documents it; the Chat SDK type does not expose it yet).
- Whether `usage` can appear on a non-final Chat chunk (docs say null except the
  last; parser accepts the last non-null).
- Per-model availability of Anthropic `output_tokens_details.thinking_tokens`.
- Chunk-boundary behavior of real providers (e.g. whether an `event:` line and
  its `data:` line ever arrive in separate TCP chunks). The decoder must handle
  it regardless.

---

## 9. Sources (all accessed 2026-10-24)

Anthropic:
- https://platform.claude.com/docs/en/build-with-claude/streaming
- https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- https://platform.claude.com/docs/en/api/messages
- https://raw.githubusercontent.com/anthropics/anthropic-sdk-python/main/src/anthropic/types/usage.py
- https://raw.githubusercontent.com/anthropics/anthropic-sdk-python/main/src/anthropic/types/message_delta_usage.py
- https://raw.githubusercontent.com/anthropics/anthropic-sdk-python/main/src/anthropic/types/cache_creation.py
- https://raw.githubusercontent.com/anthropics/anthropic-sdk-python/main/src/anthropic/types/output_tokens_details.py

OpenAI:
- https://developers.openai.com/api/reference/resources/chat/subresources/completions/streaming-events/
- https://developers.openai.com/api/docs/guides/prompt-caching
- https://developers.openai.com/api/docs/guides/streaming-responses
- https://developers.openai.com/api/reference/resources/responses/streaming-events/
- https://raw.githubusercontent.com/openai/openai-python/main/src/openai/types/completion_usage.py
- https://raw.githubusercontent.com/openai/openai-python/main/src/openai/types/chat/chat_completion_chunk.py
- https://raw.githubusercontent.com/openai/openai-python/main/src/openai/types/responses/response_usage.py
- https://raw.githubusercontent.com/openai/openai-python/main/src/openai/types/responses/response_completed_event.py
- https://raw.githubusercontent.com/openai/openai-python/main/src/openai/_streaming.py

Standards:
- https://html.spec.whatwg.org/multipage/server-sent-events.html

---

## 10. Gateways, aggregators and clients (added 2026-10-24)

This section records the provider-support decision in ADR 0006: the proxy speaks
protocols, not vendor SDKs. One OpenAI-compatible adapter plus a named upstream
covers every gateway below; only native Gemini/Ollama fidelity needs new adapters
(P6).

### 10.1 DeepSeek

- OpenAI-compatible: `https://api.deepseek.com` (and `/v1`).
- **Anthropic-compatible:** `https://api.deepseek.com/anthropic`; Claude Code can
  use it via `ANTHROPIC_BASE_URL`.
- Responses API: documented separately at `/guides/responses_api`.
- Anthropic compatibility **ignores** `cache_control`, `anthropic-version`,
  `anthropic-beta` (except Files API), `service_tier`, `container` and
  `mcp_servers`. `claude-opus*` model names map to `deepseek-v4-pro`; other
  `claude*` names map to `deepseek-flash`.
- Cache is automatic, disk-backed, prefix-unit based, with no TTL markers.
  Usage exposes `prompt_cache_hit_tokens` and `prompt_cache_miss_tokens`
  instead of `cached_tokens`.
- Profile: `usage = "deepseek"`, `cache_policy = "automatic-deepseek"`,
  `cache_hints = false` on the Anthropic surface.

### 10.2 OpenRouter

- OpenAI-compatible at `https://openrouter.ai/api/v1`; also exposes
  `/api/v1/responses` and `/api/v1/messages`.
- Usage is **always** included in the final chunk. `usage: {include: true}` and
  `stream_options.include_usage` are deprecated and have no effect.
- Usage carries `cost` and `cost_details.upstream_inference_cost`, plus
  `cached_tokens` and `cache_write_tokens`.
- The usage chunk is **not** OpenAI's shape: it contains one content-free choice
  with a repeated `finish_reason` rather than `choices: []`.
- Sends SSE comments (`: OPENROUTER PROCESSING`) and mid-stream errors as HTTP 200
  `data:` events with a top-level `error`.
- `X-Generation-Id` response header.
- Profile: `usage = "openrouter"`, `cost_source = "provider"`.

### 10.3 OpenCode (client)

- Version 2.0.31; config directory `~/.config/opencode`; providers are configured
  in `opencode.json` and backed by the AI SDK / Models.dev.
- Custom provider: `npm = "@ai-sdk/openai-compatible"` for
  `/v1/chat/completions`, or `@ai-sdk/openai` for `/v1/responses`;
  `options.baseURL` overrides the endpoint.
- `opencode run -m provider/model "message"` runs headlessly; `--standalone`
  starts a private server.
- With ChatGPT OAuth and **no** custom base URL, OpenAI traffic may use zstd or
  WebSocket; with a custom base URL it uses plain JSON (per the v2 docs).
- Implication: point `baseURL` at `http://127.0.0.1:8787/u/<name>`; no adapter is
  needed. OpenCode is the first client recipe.

### 10.4 Gemini OpenAI compatibility

- Base `https://generativelanguage.googleapis.com/v1beta/openai/`; OpenAI Chat,
  streaming and function calling are supported.
- The docs show `stream_options.include_usage`; the compatibility layer is beta
  and has known gaps (reported inflated token counts, partial `stream_options`
  support).
- Profile: `usage = "gemini-openai"`, `cache_policy = "gemini-implicit"`.
- Native Gemini adapter remains P6 for full fidelity.

### 10.5 Ollama OpenAI compatibility

- `/v1` is OpenAI-compatible; the native `/api/chat` and `/api/generate` endpoints
  return NDJSON.
- Cost is zero; token and latency telemetry still matter.
- Profile: `usage = "ollama-openai"`, `cost_source = "none"`.
- Native Ollama adapter remains P6.

### 10.6 Cross-provider boundary

Provider support only. The proxy does not choose a provider, translate between
protocols, or fall back across providers. The client's base URL selects the
upstream; the proxy forwards.

Sources (accessed 2026-10-24):
- https://api-docs.deepseek.com/guides/anthropic_api/
- https://api-docs.deepseek.com/guides/kv_cache
- https://api-docs.deepseek.com/guides/responses_api
- https://openrouter.ai/docs/api_reference/streaming
- https://openrouter.ai/docs/cookbook/administration/usage-accounting
- https://opencode.ai/docs/providers/
- https://ai.google.dev/gemini-api/docs/openai
- https://docs.ollama.com/api/openai-compatibility (OpenAI-compatible `/v1`)

---

## 11. Native Gemini and Ollama (P6)

Added 2026-10-25 from the provider reference pages below. No live captures yet;
tests use documented shapes. Anything marked **VERIFY** must be confirmed before
trusting a transform on real traffic.

### 11.1 Gemini native (`models/{model}:generateContent`)

Source (accessed 2026-10-25):
- https://ai.google.dev/api/generate-content
- https://ai.google.dev/gemini-api/docs/function-calling

Documented request shape:
- `contents[]` with `role` (`user` / `model`) and `parts[]`.
- `systemInstruction` is a `Content` object with `parts[]`.
- `tools[].functionDeclarations[]` carries `name`, `description`, `parameters`.
- A model tool call is a part `{"functionCall": {"name": ..., "args": {...}}}`.
- A tool result is a part
  `{"functionResponse": {"name": ..., "response": {...}}}`. The reference shows
  the response as a JSON object; string leaves are what the adapter can edit.
  **VERIFY** the exact response wrapper emitted by each client (SDKs and common
  MCP bridges may nest `content` or `result`).

Documented usage metadata (`usageMetadata`):
- `promptTokenCount` — total effective prompt tokens, including cached content.
- `cachedContentTokenCount` — tokens in the cached part of the prompt.
- `candidatesTokenCount` — total generated candidate tokens.
- `thoughtsTokenCount` — thinking-model thought tokens (reported separately).
- `toolUsePromptTokenCount` — tokens in tool-use prompts.
- `totalTokenCount` — total.

cxproxy normalization: `fresh_input = promptTokenCount -
cachedContentTokenCount`, `cache_read = cachedContentTokenCount`,
`output = candidatesTokenCount`, `reasoning = thoughtsTokenCount`. No cache
write fields exist for implicit/explicit Gemini caching, so writes are not
invented.

Streaming: `:streamGenerateContent` with `alt=sse` emits SSE `data:` JSON
chunks; the same `usageMetadata` shape appears on chunks (often the last one).
Non-SSE array responses are not parsed incrementally; the proxy buffers a
non-SSE JSON body and parses it at the end.

Transforms (telemetry first): segments are `tool_def` per function declaration,
`system` per system-instruction part, and `message` per content part. Only
string leaves of a `functionResponse.response` object are exposed as tool
results, so transforms never restructure Gemini JSON.

### 11.2 Ollama native (`/api/chat`, `/api/generate`)

Source (accessed 2026-10-25):
- https://docs.ollama.com/api/chat
- https://docs.ollama.com/api/generate

Documented request shape (`/api/chat`):
- `model`, `messages[]` with roles `system` / `user` / `assistant` / `tool`,
  `tools[].function`, `stream` (default **true**).
- Tool definitions are `{"type": "function", "function": {"name", ...}}`.
- Assistant tool calls are `message.tool_calls[].function` with `name` and
  object `arguments`.
- Tool results are messages with `role: "tool"` and string `content`. The
  native schema shown in the reference does not document `tool_name` on the
  message; cxproxy uses it when present and otherwise leaves the tool name
  unknown. **VERIFY** with a real client before relying on tool-name pairing.

Documented response usage (`/api/chat` final object / stream event):
- `prompt_eval_count` — number of prompt tokens.
- `prompt_eval_cached_count` — prompt tokens read from cache.
- `eval_count` — generated tokens.
- `done` — true on the final event.

cxproxy normalization: `fresh_input = prompt_eval_count -
prompt_eval_cached_count` (cache count omitted => no `cache_read` claim),
`output = eval_count`, `cost_source = none` (local model cost is zero).

Streaming: `/api/chat` and `/api/generate` return `application/x-ndjson`
by default; the parser is line-framed, not SSE. Non-streaming requests set
`stream: false` and return one JSON object. `/api/generate` has a string
`prompt` and no tool results; it is measured as one message segment.

Transforms: only string `content` on `role: "tool"` messages is exposed.

