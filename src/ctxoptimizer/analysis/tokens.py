"""Token estimation and calibration (SPEC section 12.0.2)."""

from __future__ import annotations

import importlib
import importlib.util
import math
from functools import lru_cache
from typing import Any


def _load_tiktoken() -> Any | None:
    if importlib.util.find_spec("tiktoken") is None:
        return None
    try:
        return importlib.import_module("tiktoken")
    except Exception:
        return None


_tiktoken = _load_tiktoken()


@lru_cache(maxsize=2)
def _encoding(name: str) -> Any:
    if _tiktoken is None:
        raise RuntimeError("tiktoken is not available")
    return _tiktoken.get_encoding(name)


def estimate_tokens(text: str, family: str = "generic") -> int:
    """Estimate tokens with tiktoken when available, else a stable heuristic."""
    if not text:
        return 0
    if _tiktoken is not None:
        encoding_name = "o200k_base" if family == "openai" else "cl100k_base"
        try:
            return max(1, len(_encoding(encoding_name).encode(text)))
        except Exception:
            return max(1, math.ceil(len(text) / 3.5))
    return max(1, math.ceil(len(text) / 3.5))


class Calibrator:
    """Exponential moving average of actual/estimated tokens per family."""

    def __init__(self, alpha: float = 0.1) -> None:
        self.alpha = alpha
        self.ratios: dict[str, float] = {}

    def update(self, family: str, actual: int, estimated: int) -> None:
        if estimated <= 0 or actual <= 0:
            return
        ratio = actual / estimated
        previous = self.ratios.get(family, 1.0)
        self.ratios[family] = (1 - self.alpha) * previous + self.alpha * ratio

    def apply(self, family: str, estimate: int) -> int:
        return max(0, round(estimate * self.ratios.get(family, 1.0)))


__all__ = ["Calibrator", "estimate_tokens"]
