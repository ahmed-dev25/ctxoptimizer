"""Ranked recommendations from measured evidence (SPEC section 13.7).

P2 scope: a deterministic, advisory list. Nothing is auto-applied.
"""

from __future__ import annotations

from typing import Any

from ctxoptimizer.models import WasteFinding


def recommendations(
    findings: list[WasteFinding],
    *,
    cache_serve_enabled: bool = False,
    volatile_normalizer_enabled: bool = False,
    transforms_enabled: bool = True,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[WasteFinding]] = {}
    for finding in findings:
        grouped.setdefault(finding.detector, []).append(finding)

    result: list[dict[str, Any]] = []
    rereads = grouped.get("redundant_reread", [])
    if rereads and not cache_serve_enabled:
        tokens = sum(item.est_tokens_wasted or 0 for item in rereads)
        result.append(
            {
                "id": "enable_cache_serve",
                "title": "Enable cache_serve for repeated file reads",
                "evidence": f"{len(rereads)} redundant re-read finding(s)",
                "est_tokens": tokens,
                "label": "sim.",
                "action": "set transforms.cache_serve.enabled = true",
            }
        )
    drift = grouped.get("recurring_drift", [])
    if drift and not volatile_normalizer_enabled:
        tokens = sum(item.est_tokens_wasted or 0 for item in drift)
        result.append(
            {
                "id": "enable_volatile_normalizer",
                "title": "Stabilize volatile system-prompt tokens",
                "evidence": f"{len(drift)} recurring drift finding(s)",
                "est_tokens": tokens,
                "label": "sim.",
                "action": "investigate timestamps/UUIDs in the system prompt",
            }
        )
    if grouped.get("unbatched_fanout"):
        result.append(
            {
                "id": "batch_reads",
                "title": "Batch consecutive read calls",
                "evidence": f"{len(grouped['unbatched_fanout'])} fan-out finding(s)",
                "est_tokens": 0,
                "label": "est.",
                "action": "advisory: issue independent reads together",
            }
        )
    if grouped.get("runaway_session"):
        result.append(
            {
                "id": "investigate_runaway",
                "title": "Investigate long-running unattended sessions",
                "evidence": f"{len(grouped['runaway_session'])} runaway finding(s)",
                "est_tokens": sum(
                    item.est_tokens_wasted or 0 for item in grouped["runaway_session"]
                ),
                "label": "est.",
                "action": "advisory: stop idle agents before resuming",
            }
        )
    if grouped.get("schema_bloat"):
        result.append(
            {
                "id": "prune_mcp_schemas",
                "title": "Prune unused tool schemas",
                "evidence": f"{len(grouped['schema_bloat'])} unused schema finding(s)",
                "est_tokens": sum(item.est_tokens_wasted or 0 for item in grouped["schema_bloat"]),
                "label": "sim.",
                "action": "advisory: remove MCP tools the agent never calls",
            }
        )
    if grouped.get("churn_detector"):
        result.append(
            {
                "id": "investigate_churn",
                "title": "Investigate revert/whitespace edit churn",
                "evidence": f"{len(grouped['churn_detector'])} churn finding(s)",
                "est_tokens": sum(
                    item.est_tokens_wasted or 0 for item in grouped["churn_detector"]
                ),
                "label": "est.",
                "action": "advisory: fix instructions or formatter loops",
            }
        )
    if not transforms_enabled:
        result.append(
            {
                "id": "enable_transforms",
                "title": "Enable the deterministic transform pipeline",
                "evidence": "pipeline disabled in config",
                "est_tokens": 0,
                "label": "sim.",
                "action": "set mode = active after a shadow run",
            }
        )
    result.sort(key=lambda item: int(item["est_tokens"]), reverse=True)
    return result


__all__ = ["recommendations"]
