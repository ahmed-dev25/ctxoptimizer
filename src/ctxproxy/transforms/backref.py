"""Duplicate tool-result back-references within a request (SPEC 12.6)."""

from __future__ import annotations

import time
from hashlib import sha256
from typing import Any

from ctxproxy.analysis.tokens import estimate_tokens
from ctxproxy.config import Config
from ctxproxy.models import RequestContext, TransformReport
from ctxproxy.providers.base import ProviderAdapter
from ctxproxy.transforms.ansi import clean as ansi_clean
from ctxproxy.transforms.eligibility import is_never_touch
from ctxproxy.transforms.progress import clean as progress_clean


class DuplicateBackref:
    id = "duplicate_backref"

    def applies(
        self, ctx: RequestContext, payload: dict[str, Any], adapter: ProviderAdapter
    ) -> bool:
        return ctx.config.transforms.duplicate_backref.enabled

    def apply(
        self,
        ctx: RequestContext,
        payload: dict[str, Any],
        adapter: ProviderAdapter,
        config: Config,
    ) -> TransformReport:
        started = time.perf_counter()
        settings = config.transforms.duplicate_backref
        seen: dict[bytes, str] = {}
        items = 0
        bytes_before = 0
        bytes_after = 0
        tokens_before = 0
        tokens_after = 0
        for ref in adapter.iter_tool_results(payload):
            if is_never_touch(ref, config) and not settings.include_never_touch:
                continue
            text = ref.get_text()
            if text is None or len(text.encode("utf-8")) < settings.min_bytes:
                continue
            sigma = progress_clean(ansi_clean(text))
            digest = sha256(sigma.encode("utf-8")).digest()
            if digest not in seen:
                seen[digest] = ref.tool_use_id or "earlier"
                continue
            stub = f"[ctxproxy: output identical to earlier tool result {seen[digest]}]"
            if len(stub.encode("utf-8")) >= len(text.encode("utf-8")):
                continue
            items += 1
            bytes_before += len(text.encode("utf-8"))
            bytes_after += len(stub.encode("utf-8"))
            tokens_before += estimate_tokens(text)
            tokens_after += estimate_tokens(stub)
            ref.set_text(stub)
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


__all__ = ["DuplicateBackref"]
