"""ANSI and control-character stripping (SPEC section 12.1)."""

from __future__ import annotations

import re

CSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
OSC = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
ESC = re.compile(r"\x1b[@-Z\\-_]")
C0 = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def clean(text: str) -> str:
    """Remove ANSI CSI/OSC/ESC sequences and stray C0 controls."""
    text = CSI.sub("", text)
    text = OSC.sub("", text)
    text = ESC.sub("", text)
    return C0.sub("", text)


__all__ = ["clean"]
