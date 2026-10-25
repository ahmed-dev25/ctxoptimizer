# FAQ

## Why is my cache hit ratio low?

Open the dashboard **Waste** page. The most common causes are:

1. A changing system prompt (timestamp, UUID, shell banner). Look for
   `system_changed` drift and `recurring_drift` findings.
2. Tool schemas changing order or content (`tools_changed`).
3. The client compacting or editing earlier history (`history_mutated`).
4. An idle gap longer than the provider cache TTL (`ttl_expired`).
5. For Anthropic, missing or poorly placed `cache_control` breakpoints; the
   `anthropic_cache` transform adds a stair-step set when active.
6. For OpenAI-compatible servers, no stable `prompt_cache_key`; enable
   `openai_hints` in active mode where the provider supports it.

## Are the savings real?

Only provider-reported usage and cost are billed facts. Baseline, waste and
savings figures are labelled `est.` or `sim.` and computed from the recorded
request metadata. The Overview shows actual spend separately from simulated
baseline/savings.

## What is shadow vs active?

- `shadow` measures and simulates; forwarded bytes are unchanged.
- `active` applies enabled transforms, with a retry-with-original on 400/422.
- `passthrough` measures usage only.

Start in shadow, inspect the Waste/Transforms pages, then switch to active.

## Will the proxy break my client?

It is fail-open by design: transform errors are discarded, a no-regression
guard reverts changes that do not save enough tokens, and an upstream 400/422
retries the original bytes. A session-scoped guard quarantines a transform
after repeated fallbacks. If something still breaks, run with
`x-ctxoptimizer-bypass: 1` and open the request detail page.

## Where is the dashboard token?

It is printed in the startup banner. Open the URL once; the cookie is set for
`/_ctxoptimizer`. Restarting the proxy rotates the token.

## Can I use Cursor / a browser extension?

Only clients that let you change the provider base URL can be proxied. Cursor's
backend traffic cannot be redirected locally. See `docs/client-setup.md`.

## Why is a model unpriced?

The bundled pricing table only contains verified/public rates. Unknown models
stay unpriced rather than inventing a number; add an override in the Pricing
page or `pricing.json`.

## Is ctxoptimizer open source?

Yes. ctxoptimizer is free and open-source software under the MIT License. There is
no license key, activation step or active-mode gate. See `LICENSE`.
