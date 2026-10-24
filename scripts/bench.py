"""Synthetic pipeline benchmark (SPEC section 18). Prints p50/p95 overhead.

This is a smoke benchmark, not a CI regression gate: it uses a generated corpus
and requires no provider keys.
"""

from __future__ import annotations

import statistics
import time

from ctxproxy.config import Config
from ctxproxy.models import Endpoint, Mode, Provider, RequestContext
from ctxproxy.pipeline import run_pipeline
from ctxproxy.providers import adapter_for
from ctxproxy.transforms import build_transforms


def _payload(size: int) -> dict[str, object]:
    messages: list[dict[str, object]] = [{"role": "user", "content": "inspect the repo"}]
    for index in range(size):
        messages.append(
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": f"t{index}",
                        "name": "Bash",
                        "input": {"command": "pytest -q"},
                    }
                ],
            }
        )
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": f"t{index}",
                        "content": ("line of test output\n" * 80)
                        + ("\x1b[31mFAILED\x1b[0m\n" * 20),
                    }
                ],
            }
        )
    return {"model": "claude-sonnet-4-5", "messages": messages}


def main() -> None:
    config = Config.model_validate({"mode": {"default": "active"}})
    adapter = adapter_for(Provider.ANTHROPIC, Endpoint.MESSAGES)
    rounds = 25
    samples: list[float] = []
    for _ in range(rounds):
        payload = _payload(40)
        ctx = RequestContext(
            request_id="bench",
            provider=Provider.ANTHROPIC,
            endpoint=Endpoint.MESSAGES,
            upstream_name="anthropic",
            model="claude-sonnet-4-5",
            stream=False,
            mode=Mode.ACTIVE,
            session_id="bench",
            project="bench",
            client_name="bench",
            config=config,
            config_hash=config.config_hash,
            started_monotonic=time.monotonic(),
        )
        started = time.perf_counter()
        run_pipeline(ctx, payload, adapter, build_transforms(config), config)
        samples.append((time.perf_counter() - started) * 1000)
    samples.sort()
    p50 = statistics.median(samples)
    p95 = samples[int(len(samples) * 0.95) - 1]
    print(f"rounds={rounds} corpus_tool_results=40")
    print(f"p50_ms={p50:.2f} p95_ms={p95:.2f} max_ms={max(samples):.2f}")
    print("note: synthetic corpus; publish measured numbers with hardware details")


if __name__ == "__main__":
    main()
