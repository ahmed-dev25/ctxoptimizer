"""Deterministic payload transforms and the P3/P4 registry (SPEC section 12)."""

from __future__ import annotations

from ctxproxy.config import Config
from ctxproxy.transforms import ansi, dedupe_lines, progress, truncate, whitespace
from ctxproxy.transforms.anthropic_cache import AnthropicCache
from ctxproxy.transforms.backref import DuplicateBackref
from ctxproxy.transforms.base import TextTransform, Transform
from ctxproxy.transforms.cache_serve import CacheServe, CacheServeState
from ctxproxy.transforms.eligibility import is_compactable, is_never_touch
from ctxproxy.transforms.openai_hints import OpenAIHints


def build_transforms(
    config: Config,
    *,
    disabled: set[str] | None = None,
    cache_serve_state: CacheServeState | None = None,
) -> list[Transform]:
    """Return enabled transforms in the fixed pipeline order."""
    transforms = config.transforms
    removed = disabled or set()
    result: list[Transform] = []

    def add(transform: Transform) -> None:
        if transform.id not in removed:
            result.append(transform)

    if transforms.ansi_strip.enabled:
        add(
            TextTransform(
                "ansi_strip",
                ansi.clean,
                eligible=lambda ref: not is_never_touch(ref, config),
            )
        )
    if transforms.progress_collapse.enabled:
        add(
            TextTransform(
                "progress_collapse",
                progress.clean,
                eligible=lambda ref: not is_never_touch(ref, config),
            )
        )
    if transforms.line_dedupe.enabled:
        add(
            TextTransform(
                "line_dedupe",
                lambda text: dedupe_lines.clean(text, transforms.line_dedupe.min_repeat),
                eligible=lambda ref: is_compactable(ref, config),
            )
        )
    if transforms.whitespace_trim.enabled:
        add(
            TextTransform(
                "whitespace_trim",
                lambda text: whitespace.clean(text, transforms.whitespace_trim.max_blank_run),
                eligible=lambda ref: is_compactable(ref, config),
            )
        )
    if transforms.smart_truncate.enabled:
        add(
            TextTransform(
                "smart_truncate",
                lambda text: truncate.clean(text, transforms.smart_truncate),
                eligible=lambda ref: is_compactable(ref, config),
            )
        )
    if transforms.duplicate_backref.enabled:
        add(DuplicateBackref())
    if transforms.cache_serve.enabled and cache_serve_state is not None:
        add(CacheServe(cache_serve_state))
    if transforms.anthropic_cache.enabled:
        add(AnthropicCache())
    if transforms.openai_hints.enabled:
        add(OpenAIHints())
    return result


__all__ = ["build_transforms"]
