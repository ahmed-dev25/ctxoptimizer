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
        if not settings.enabled:
            return False
        if ctx.provider is not Provider.OPENAI:
            return False
        if ctx.endpoint not in {Endpoint.CHAT, Endpoint.RESPONSES}:
            return False
        entry = ctx.config.upstreams.get(ctx.upstream_name)
        if entry is None:
            return False
        url = entry if isinstance(entry, str) else entry.url
        if (urlsplit(url).hostname or "").lower() != "api.openai.com":
            return False
        if settings.send_prompt_cache_key and "prompt_cache_key" not in payload:
            return True
        if (
            settings.inject_stream_usage
            and ctx.endpoint is Endpoint.CHAT
            and payload.get("stream") is True
        ):
            options = payload.get("stream_options")
            return not isinstance(options, dict) or options.get("include_usage") is not True
        return False

    def apply(
        self,
        ctx: RequestContext,
        payload: dict[str, Any],
        adapter: ProviderAdapter,
        config: Config,
    ) -> TransformReport:
        started = time.perf_counter()
        settings = config.transforms.openai_hints
        changed = False
        notes: dict[str, object] = {}
        if settings.send_prompt_cache_key and "prompt_cache_key" not in payload:
            key = "ctxp-" + sha256(ctx.session_id.encode("utf-8")).hexdigest()[:24]
            payload["prompt_cache_key"] = key
            notes["key"] = key
            changed = True
        if (
            settings.inject_stream_usage
            and ctx.endpoint is Endpoint.CHAT
            and payload.get("stream") is True
        ):
            options = payload.get("stream_options")
            if not isinstance(options, dict):
                options = {}
                payload["stream_options"] = options
            if options.get("include_usage") is not True:
                options["include_usage"] = True
                notes["inject_stream_usage"] = True
                changed = True
        return TransformReport(
            transform_id=self.id,
            ran=True,
            changed=changed,
            items_touched=len(notes),
            duration_ms=(time.perf_counter() - started) * 1000,
            notes=notes,
        )


__all__ = ["OpenAIHints"]
