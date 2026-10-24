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
5. **OpenCode `--standalone` credentials.** Does a private server read the stored
   DeepSeek credential, or only the background service? If not, the smoke test
   needs the background service or an exported credential.

## Client configuration

6. **OpenCode base path.** Which path does the built-in DeepSeek provider append to
   `options.baseURL` (`/chat/completions` or `/v1/chat/completions`)? The proxy
   should be tested with both.
7. **Codex CLI base URL.** Does the installed Codex CLI honor a custom base URL
   when signed in with ChatGPT, or does it always use OpenAI's backend?
8. **Cursor.** Confirm it remains unproxyable (traffic goes through Cursor's
   servers).

## Pricing

9. Which DeepSeek model IDs are current for your account (`deepseek-flash`,
   `deepseek-v4-pro`, `deepseek-chat`, `deepseek-reasoner`)? Pricing entries are
   keyed by exact model id.
10. Do you want bundle/priority/long-context tiers priced in v1, or is the base
    per-million-token rate sufficient (SPEC §14.2 says unsupported)?

## Product

11. Should `v0.1.0-alpha` be tagged after P1, or wait until the dashboard (P2/P5)?
