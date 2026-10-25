"""Canonical segments and content hashing (SPEC section 13.3)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from hashlib import blake2b
from typing import Any, Literal

import orjson

from ctxoptimizer.analysis.tokens import estimate_tokens


@dataclass(frozen=True, slots=True)
class Segment:
    kind: Literal["tool_def", "system", "message"]
    msg_index: int | None
    block_index: int | None
    hash: bytes
    est_tokens: int
    has_marker: bool


def block_hash(block: dict[str, Any]) -> bytes:
    """Stable 8-byte hash of a block, ignoring cache markers."""
    clean = {key: value for key, value in block.items() if key != "cache_control"}
    encoded = orjson.dumps(clean, option=orjson.OPT_SORT_KEYS)
    return blake2b(encoded, digest_size=8).digest()


def block_tokens(block: dict[str, Any]) -> int:
    for key in ("text", "content"):
        value = block.get(key)
        if isinstance(value, str):
            return estimate_tokens(value)
    return max(1, math.ceil(len(orjson.dumps(block)) / 3.5))


def make_segment(
    kind: Literal["tool_def", "system", "message"],
    block: dict[str, Any],
    *,
    msg_index: int | None = None,
    block_index: int | None = None,
) -> Segment:
    return Segment(
        kind=kind,
        msg_index=msg_index,
        block_index=block_index,
        hash=block_hash(block),
        est_tokens=block_tokens(block),
        has_marker="cache_control" in block,
    )


__all__ = ["Segment", "block_hash", "block_tokens", "make_segment"]
