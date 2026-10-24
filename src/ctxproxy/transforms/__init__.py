"""Deterministic payload transforms and the P3 registry (SPEC section 12)."""

from __future__ import annotations

from ctxproxy.config import Config
from ctxproxy.transforms import ansi, dedupe_lines, progress, truncate, whitespace
from ctxproxy.transforms.backref import DuplicateBackref
from ctxproxy.transforms.base import TextTransform, Transform
from ctxproxy.transforms.eligibility import is_compactable, is_never_touch


def build_transforms(config: Config) -> list[Transform]:
    """Return enabled transforms in the fixed pipeline order."""
    transforms = config.transforms
    result: list[Transform] = []
    if transforms.ansi_strip.enabled:
        result.append(
            TextTransform(
                "ansi_strip",
                ansi.clean,
                eligible=lambda ref: not is_never_touch(ref, config),
            )
        )
    if transforms.progress_collapse.enabled:
        result.append(
            TextTransform(
                "progress_collapse",
                progress.clean,
                eligible=lambda ref: not is_never_touch(ref, config),
            )
        )
    if transforms.line_dedupe.enabled:
        result.append(
            TextTransform(
                "line_dedupe",
                lambda text: dedupe_lines.clean(text, transforms.line_dedupe.min_repeat),
                eligible=lambda ref: is_compactable(ref, config),
            )
        )
    if transforms.whitespace_trim.enabled:
        result.append(
            TextTransform(
                "whitespace_trim",
                lambda text: whitespace.clean(text, transforms.whitespace_trim.max_blank_run),
                eligible=lambda ref: is_compactable(ref, config),
            )
        )
    if transforms.smart_truncate.enabled:
        result.append(
            TextTransform(
                "smart_truncate",
                lambda text: truncate.clean(text, transforms.smart_truncate),
                eligible=lambda ref: is_compactable(ref, config),
            )
        )
    if transforms.duplicate_backref.enabled:
        result.append(DuplicateBackref())
    return result


__all__ = ["build_transforms"]
