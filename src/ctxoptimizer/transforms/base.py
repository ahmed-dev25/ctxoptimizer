"""Transform protocol and the pure-text transform driver (SPEC section 12.0.1)."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, Protocol

from ctxoptimizer.analysis.tokens import estimate_tokens
from ctxoptimizer.config import Config
from ctxoptimizer.models import RequestContext, ToolResultRef, TransformReport
from ctxoptimizer.providers.base import ProviderAdapter


class Transform(Protocol):
    id: str

    def applies(
        self, ctx: RequestContext, payload: dict[str, Any], adapter: ProviderAdapter
    ) -> bool: ...

    def apply(
        self,
        ctx: RequestContext,
        payload: dict[str, Any],
        adapter: ProviderAdapter,
        config: Config,
    ) -> TransformReport: ...


class TextTransform:
    """Run a pure ``str -> str`` function over every eligible tool result."""

    def __init__(
        self,
        transform_id: str,
        clean: Callable[[str], str],
        *,
        enabled: bool = True,
        eligible: Callable[[ToolResultRef], bool] | None = None,
    ) -> None:
        self.id = transform_id
        self._clean = clean
        self._enabled = enabled
        self._eligible = eligible or (lambda ref: True)

    def applies(
        self, ctx: RequestContext, payload: dict[str, Any], adapter: ProviderAdapter
    ) -> bool:
        return self._enabled

    def apply(
        self,
        ctx: RequestContext,
        payload: dict[str, Any],
        adapter: ProviderAdapter,
        config: Config,
    ) -> TransformReport:
        started = time.perf_counter()
        items = 0
        bytes_before = 0
        bytes_after = 0
        tokens_before = 0
        tokens_after = 0
        for ref in adapter.iter_tool_results(payload):
            if not self._eligible(ref):
                continue
            text = ref.get_text()
            if text is None:
                continue
            new_text = self._clean(text)
            if new_text == text:
                continue
            items += 1
            bytes_before += len(text.encode("utf-8"))
            bytes_after += len(new_text.encode("utf-8"))
            tokens_before += estimate_tokens(text)
            tokens_after += estimate_tokens(new_text)
            ref.set_text(new_text)
        return TransformReport(
            transform_id=self.id,
            ran=True,
            changed=items > 0,
            items_touched=items,
            bytes_before=bytes_before,
            bytes_after=bytes_after,
            est_tokens_before=tokens_before,
            est_tokens_after=tokens_after,
            duration_ms=(time.perf_counter() - started) * 1000,
        )


__all__ = ["TextTransform", "Transform"]
