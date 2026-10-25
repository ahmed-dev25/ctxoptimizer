"""Synthetic pipeline benchmark (SPEC section 18). Prints p50/p95 overhead.

This is a smoke benchmark, not a CI regression gate: it uses a generated corpus
and requires no provider keys.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

from ctxoptimizer.config import Config
from ctxoptimizer.models import Endpoint, Mode, Provider, RequestContext
from ctxoptimizer.pipeline import run_pipeline
from ctxoptimizer.providers import adapter_for
from ctxoptimizer.transforms import build_transforms


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
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=25)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--baseline", type=str, default=None)
    parser.add_argument("--tolerance", type=float, default=0.20)
    args = parser.parse_args()
    config = Config.model_validate({"mode": {"default": "active"}})
    adapter = adapter_for(Provider.ANTHROPIC, Endpoint.MESSAGES)
    rounds = max(1, args.rounds)
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
    result = {
        "rounds": rounds,
        "corpus_tool_results": 40,
        "p50_ms": round(p50, 2),
        "p95_ms": round(p95, 2),
        "max_ms": round(max(samples), 2),
        "note": "synthetic corpus; publish measured numbers with hardware details",
    }
    if args.json:
        print(json.dumps(result))
    else:
        print(f"rounds={rounds} corpus_tool_results=40")
        print(f"p50_ms={p50:.2f} p95_ms={p95:.2f} max_ms={max(samples):.2f}")
        print(result["note"])
    if args.baseline:
        baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
        allowed = float(baseline["p95_ms"]) * (1 + args.tolerance)
        if p95 > allowed:
            print(
                f"p95 regression: {p95:.2f}ms > {allowed:.2f}ms (baseline {baseline['p95_ms']}ms)",
                file=sys.stderr,
            )
            raise SystemExit(1)


if __name__ == "__main__":
    main()
