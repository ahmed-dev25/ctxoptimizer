"""Exact and near-duplicate line collapsing (SPEC section 12.3)."""

from __future__ import annotations

import re

SIGNAL = re.compile(
    r"error|fail(?:ed|ure)?|exception|fatal|warning|traceback|panic",
    re.IGNORECASE,
)
_TS = re.compile(r"\b\d{4}-\d{2}-\d{2}T\S+|\b\d{2}:\d{2}:\d{2}\b")
_HEX = re.compile(r"\b[0-9a-f]{8,}\b", re.IGNORECASE)
_DIGITS = re.compile(r"\d+")


def clean(text: str, min_repeat: int = 3) -> str:
    lines = text.split("\n")
    exact: list[str] = []
    index = 0
    while index < len(lines):
        end = index
        while end + 1 < len(lines) and lines[end + 1].rstrip() == lines[index].rstrip():
            end += 1
        run = end - index + 1
        if run >= min_repeat:
            exact.append(lines[index])
            exact.append(f"[ctxproxy: line repeated {run - 1} more times]")
        else:
            exact.extend(lines[index : end + 1])
        index = end + 1
    return "\n".join(_collapse_near(exact, min_repeat))


def _collapse_near(lines: list[str], min_repeat: int) -> list[str]:
    result: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("[ctxproxy:") or SIGNAL.search(line):
            result.append(line)
            index += 1
            continue
        key = _normalise(line)
        end = index
        while (
            end + 1 < len(lines)
            and not lines[end + 1].startswith("[ctxproxy:")
            and not SIGNAL.search(lines[end + 1])
            and _normalise(lines[end + 1]) == key
        ):
            end += 1
        run = end - index + 1
        if run >= 2 * min_repeat:
            result.append(lines[index])
            result.append(f"[ctxproxy: {run - 2} similar lines omitted]")
            result.append(lines[end])
        else:
            result.extend(lines[index : end + 1])
        index = end + 1
    return result


def _normalise(line: str) -> str:
    line = _TS.sub("<ts>", line)
    line = _HEX.sub("<id>", line)
    return _DIGITS.sub("#", line)


__all__ = ["clean"]
