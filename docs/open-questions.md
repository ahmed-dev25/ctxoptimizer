# Open questions (for the owner)

Created 2026-10-24 during the P1 build. Items here are deliberately not guessed;
the code takes the conservative path and this file records what needs confirmation.

## Provider behavior

1. **OpenRouter cost units.** `usage.cost` is documented as "credits". Is 1 credit
   exactly 1 USD for our purposes, and should `provider_cost_usd` be populated
   directly from it? `cost_details.upstream_inference_cost` is only meaningful for
   BYOK requests.
2. **Gemini OpenAI-compat usage.** Does `/v1beta/openai/chat/completions` reliably
   honor `stream_options.include_usage`, and are `cached_tokens` / `prompt_tokens`
   accurate? Several community reports mention inflated counts.
3. **Ollama OpenAI-compat usage.** Does `/v1/chat/completions` return a `usage`
   object, or only the native `/api/chat` `prompt_eval_count` / `eval_count`?
4. **DeepSeek Anthropic surface.** Does `https://api.deepseek.com/anthropic` emit
   `message_start`/`message_delta` usage with cache fields like Anthropic, and does
   it stream `event: error` the same way? Its docs say `cache_control` is ignored.
5. **OpenCode `--standalone` credentials. — RESOLVED 2026-10-25.** The private
   server read the stored DeepSeek credential and the run succeeded without
   exporting or printing any secret.

## Client configuration

6. **OpenCode base path. — RESOLVED 2026-10-25.** With
   `baseURL = http://127.0.0.1:8787/u/deepseek`, OpenCode appended
   `/chat/completions` (no `/v1`), and the proxy forwarded it correctly.
7. **Codex CLI base URL.** Does the installed Codex CLI honor a custom base URL
   when signed in with ChatGPT, or does it always use OpenAI's backend?
8. **Cursor.** Confirm it remains unproxyable (traffic goes through Cursor's
   servers).

## Pricing

9. ~~Which DeepSeek model IDs are current for your account (`deepseek-flash`,
   `deepseek-v4-pro`, `deepseek-chat`, `deepseek-reasoner`)?~~ **Partially
   resolved:** `deepseek-flash` is confirmed and priced. `deepseek-v4-pro` is
   priced from the docs but not exercised live.
10. Do you want bundle/priority/long-context tiers priced in v1, or is the base
    per-million-token rate sufficient (SPEC §14.2 says unsupported)?

## Product

11. Should `v0.1.0-alpha` be tagged after P1, or wait until the dashboard (P2/P5)?
12. **DeepSeek peak vs off-peak pricing.** The table uses peak rates as the
    conservative default (off-peak is half). Should the proxy choose by UTC time,
    or keep peak as the honest upper bound?
13. **OpenCode side requests.** One `opencode run` produced three requests
    (title/side calls plus the main turn). Session derivation (P2-1) should group
    them; confirm whether that matches your expectation of one "session".
14. **Gemini native tool-result wrapper. — NEEDS CAPTURE.** The documented
    `functionResponse.response` is an object, but SDKs/MCP bridges may nest the
    payload under `content`, `result`, `output`, or return a plain string. The
    adapter handles all four string-leaf forms; confirm with one real Gemini
    function-calling capture which form your clients emit.
15. **Ollama native tool results. — NEEDS CAPTURE.** The native `/api/chat`
    schema documents `role: "tool"` with `content` but does not show a
    `tool_name` field. cxproxy uses `tool_name` when present; confirm how your
    client pairs the result with the assistant's tool call.
16. **W7 edit-tool schemas. — VERIFY before trusting.** The opt-in churn
    detector recognizes `old_string`/`new_string`, `oldText`/`newText`,
    `old_str`/`new_str`, `old_content`/`new_content`, `search`/`replace`, and
    `old`/`new`, plus common path keys. Confirm each agent's actual edit schema
    (Claude Code, Cursor, OpenCode, Codex) so W7 is not silently blind.
17. **`stale_result_elision` break-even UX. — RESOLVED 2026-10-25.** The
    Transforms page now includes a conservative `sim.` break-even calculator
    backed by `/api/stale-elision/estimate`; the transform remains off by
    default.

