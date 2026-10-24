"""Byte-true cross-request substitution (SPEC section 12.12)."""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from ctxproxy.analysis.tokens import estimate_tokens
from ctxproxy.config import Config
from ctxproxy.models import RequestContext, TransformReport
from ctxproxy.providers.base import ProviderAdapter
from ctxproxy.transforms.ansi import clean as ansi_clean
from ctxproxy.transforms.progress import clean as progress_clean


@dataclass(slots=True)
class CacheEntry:
    hash: bytes
    size: int
    first_turn: int
    ref: str


class CacheServeState:
    """Bounded per-session content map (INV-17 says no silent loss)."""

    def __init__(self, max_sessions: int = 256, max_entries: int = 512) -> None:
        self.max_sessions = max_sessions
        self.max_entries = max_entries
        self._sessions: OrderedDict[str, OrderedDict[bytes, CacheEntry]] = OrderedDict()

    def session(self, session_id: str) -> OrderedDict[bytes, CacheEntry]:
        entries = self._sessions.get(session_id)
        if entries is None:
            if len(self._sessions) >= self.max_sessions:
                self._sessions.popitem(last=False)
            entries = OrderedDict()
            self._sessions[session_id] = entries
        else:
            self._sessions.move_to_end(session_id)
        return entries

    def put(self, entries: OrderedDict[bytes, CacheEntry], entry: CacheEntry) -> None:
        entries[entry.hash] = entry
        entries.move_to_end(entry.hash)
        while len(entries) > self.max_entries:
            entries.popitem(last=False)

    def entries(self, session_id: str) -> dict[bytes, CacheEntry]:
        return dict(self.session(session_id))


class CacheServe:
    id = "cache_serve"

    def __init__(self, state: CacheServeState) -> None:
        self.state = state

    def applies(
        self, ctx: RequestContext, payload: dict[str, Any], adapter: ProviderAdapter
    ) -> bool:
        return (
            ctx.config.transforms.cache_serve.enabled
            and ctx.config.telemetry.capture_payloads != "off"
        )

    def apply(
        self,
        ctx: RequestContext,
        payload: dict[str, Any],
        adapter: ProviderAdapter,
        config: Config,
    ) -> TransformReport:
        started = time.perf_counter()
        settings = config.transforms.cache_serve
        turns = _assistant_turns(payload)
        boundary = max(
            0,
            ((turns - settings.keep_recent_turns) // settings.batch_turns) * settings.batch_turns,
        )
        entries = self.state.session(ctx.session_id)
        seen: set[bytes] = set()
        stubs = 0
        tokens_before = 0
        tokens_after = 0
        for ref in adapter.iter_tool_results(payload):
            text = ref.get_text()
            if text is None or len(text.encode("utf-8")) < settings.min_bytes:
                continue
            sigma = progress_clean(ansi_clean(text))
            digest = sha256(sigma.encode("utf-8")).digest()
            if digest in seen:
                continue
            seen.add(digest)
            entry = entries.get(digest)
            if (
                entry is not None
                and entry.first_turn < boundary
                and stubs < settings.max_stubs_per_request
            ):
                stub = (
                    f"[ctxproxy: content identical to turn {entry.first_turn} "
                    f"({entry.size / 1024:.1f} KB, sha256 {entry.ref}...); unchanged. "
                    f"reread ref={entry.ref} | ctxproxy_expand({entry.ref}) retrieves it]"
                )
                if len(stub.encode("utf-8")) < len(text.encode("utf-8")):
                    tokens_before += estimate_tokens(text)
                    tokens_after += estimate_tokens(stub)
                    ref.set_text(stub)
                    stubs += 1
                continue
            if entry is None:
                self.state.put(
                    entries,
                    CacheEntry(
                        hash=digest,
                        size=len(text.encode("utf-8")),
                        first_turn=turns,
                        ref=sha256(text.encode("utf-8")).hexdigest()[:8],
                    ),
                )
        return TransformReport(
            transform_id=self.id,
            ran=True,
            changed=stubs > 0,
            items_touched=stubs,
            est_tokens_before=tokens_before,
            est_tokens_after=tokens_after,
            duration_ms=(time.perf_counter() - started) * 1000,
            notes={"boundary": boundary, "turns": turns, "stubs": stubs},
        )


def _assistant_turns(payload: dict[str, Any]) -> int:
    items = payload.get("messages")
    if not isinstance(items, list):
        items = payload.get("input")
    if not isinstance(items, list):
        return 0
    return sum(1 for item in items if isinstance(item, dict) and item.get("role") == "assistant")


__all__ = ["CacheEntry", "CacheServe", "CacheServeState"]
