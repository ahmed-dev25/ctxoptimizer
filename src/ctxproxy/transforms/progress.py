"""Progress-bar and carriage-return collapsing (SPEC section 12.2)."""

from __future__ import annotations

import re

PROGRESS = re.compile(
    r"(?:[#=>█▉▊▋▌▍▎▏.\- ]{8,}\s*\d{1,3}%"
    r"|\b\d+(?:\.\d+)?\s?(?:kB|MB|GB|KiB|MiB)/s\b"
    r"|^(?:Downloading|Fetching|Receiving objects|Resolving deltas|"
    r"Compressing objects|Unpacking|Counting objects|Collecting|Installing)\b"
    r".*?(?:\d{1,3}%|\d+\s?(?:kB|MB|GB|KiB|MiB)))",
    re.IGNORECASE,
)
SIGNAL = re.compile(r"error|fail|fatal|warning", re.IGNORECASE)


def clean(text: str) -> str:
    lines = [_last_carriage_segment(line) for line in text.split("\n")]
    result: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not _is_progress(line):
            result.append(line)
            index += 1
            continue
        end = index
        while end + 1 < len(lines) and _is_progress(lines[end + 1]):
            end += 1
        run = end - index + 1
        if run >= 3:
            result.append(f"[ctxproxy: {run} progress updates collapsed]")
            result.append(lines[end])
        else:
            result.extend(lines[index : end + 1])
        index = end + 1
    return "\n".join(result)


def _last_carriage_segment(line: str) -> str:
    if "\r" not in line:
        return line
    segments = [part for part in line.split("\r") if part]
    return segments[-1] if segments else ""


def _is_progress(line: str) -> bool:
    return bool(PROGRESS.search(line)) and not SIGNAL.search(line)


__all__ = ["clean"]
