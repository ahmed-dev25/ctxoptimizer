"""Secret redaction for stored copies (SPEC section 14.4).

Redaction applies only to blobs/exports written to disk, never to forwarded
traffic. Patterns are linear-time and conservative: when in doubt, redact.
"""

from __future__ import annotations

import re

_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_\-]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}"),
    re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
        re.DOTALL,
    ),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-+/=]{8,}"),
    re.compile(
        r"(?im)^([ \t]*(?:export[ \t]+)?[A-Za-z0-9_.-]*"
        r"(?:secret|token|password|passwd|api[_-]?key)[A-Za-z0-9_.-]*[ \t]*=[ \t]*)"
        r"(\"[^\"]*\"|'[^']*'|[^\s#]+)"
    ),
)

_REDACTED = "[REDACTED]"


def redact_text(text: str) -> str:
    """Return *text* with recognized credentials replaced."""
    if not text:
        return text
    for pattern in _PATTERNS[:-1]:
        text = pattern.sub(_REDACTED, text)
    text = _PATTERNS[-1].sub(lambda match: match.group(1) + _REDACTED, text)
    return text


def redact_bytes(data: bytes) -> bytes:
    """Best-effort UTF-8 decoding so binary blobs are never damaged."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return data
    return redact_text(text).encode("utf-8")


__all__ = ["redact_bytes", "redact_text"]
