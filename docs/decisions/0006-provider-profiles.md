# 0006 — Protocol-first provider support with named upstreams and profiles

- Status: accepted
- Date: 2026-10-24
- Spec refs: §1.3, §8.3, §11, §12.10, §13.5, §14.1, §14.2

## Context

The first target list grew from Anthropic/OpenAI/Ollama to "every major coding
agent": DeepSeek, OpenRouter, OpenCode, Gemini, local servers and the long tail of
OpenAI-compatible gateways. Writing one adapter per vendor is not viable (OpenCode
alone lists 75+ providers), and the SPEC already anticipated the correct shape in
§8.3 with named upstreams.

## Decision

1. Support **protocols**, not vendors: Anthropic Messages, OpenAI Chat
   Completions, OpenAI Responses, plus native Gemini/Ollama in P6.
2. Every other provider is a **named upstream** with a `kind` selecting one of
   those protocols. `/u/<name>/**` strips the prefix and forwards the remainder.
3. Each upstream carries a **profile**:
   - `usage`: `anthropic` | `openai` | `deepseek` | `openrouter` |
     `gemini-openai` | `ollama-openai`
   - `cache_policy`: `explicit-anthropic` | `implicit-openai` |
     `automatic-deepseek` | `gemini-implicit` | `none`
   - `cost_source`: `pricing` | `provider` | `none`
   - `cache_hints`: whether provider-specific cache markers may be injected
   - `inject_stream_usage`: whether to request usage on the stream
4. Provider-reported cost (OpenRouter `usage.cost`) is preferred over table
   pricing when `cost_source = "provider"`.
5. No cross-provider routing, translation or fallback. The client selects the
   upstream.

## Consequences

- DeepSeek, OpenRouter, Gemini (OpenAI-compat), Ollama (OpenAI-compat), LM Studio,
  vLLM, Groq, Together, Fireworks, Cerebras, Moonshot, xAI and similar hosts are
  supported without new adapters.
- Cache simulation must be policy-driven per upstream. Applying Anthropic TTL
  rules to DeepSeek would produce wrong savings numbers.
- Native Gemini/Ollama adapters remain P6 for full-fidelity transforms, not for
  basic support.
- Unknown or non-compliant gateways degrade to `usage_source="none"` rather than
  inventing numbers (INV-13).
