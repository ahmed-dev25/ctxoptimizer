"""OpenAI prompt_cache_key hints (SPEC section 12.10)."""

from __future__ import annotations

import time
from hashlib import sha256
from typing import Any
from urllib.parse import urlsplit

from ctxproxy.config import Config
from ctxproxy.models import Endpoint, Provider, RequestContext, TransformReport
from ctxproxy.providers.base import ProviderAdapter


class OpenAIHints:
    id = "openai_hints"

    def applies(
        self, ctx: RequestContext, payload: dict[str, Any], adapter: ProviderAdapter
    ) -> bool:
        settings = ctx.config.transforms.openai_hints
        if not settings.enabled or not settings.send_prompt_cache_key:
            return False
        if ctx.provider is not Provider.OPENAI:
            return False
        if ctx.endpoint not in {Endpoint.CHAT, Endpoint.RESPONSES}:
            return False
        if "prompt_cache_key" in payload:
            return False
        entry = ctx.config.upstreams.get(ctx.upstream_name)
        if entry is None:
            return False
        url = entry if isinstance(entry, str) else entry.url
        return (urlsplit(url).hostname or "").lower() == "api.openai.com"

    def apply(
        self,
        ctx: RequestContext,
        payload: dict[str, Any],
        adapter: ProviderAdapter,
        config: Config,
    ) -> TransformReport:
        started = time.perf_counter()
        key = "ctxp-" + sha256(ctx.session_id.encode("utf-8")).hexdigest()[:24]
        payload["prompt_cache_key"] = key
        return TransformReport(
            transform_id=self.id,
            ran=True,
            changed=True,
            items_touched=1,
            duration_ms=(time.perf_counter() - started) * 1000,
            notes={"key": key},
        )


__all__ = ["OpenAIHints"]
