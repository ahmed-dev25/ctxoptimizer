"""Error-aware truncation with signal windows (SPEC section 12.5)."""

from __future__ import annotations

import re
from hashlib import sha256

from ctxproxy.config import SmartTruncateConfig

SIGNAL = re.compile(
    r"error|fail(?:ed|ure)?|exception|traceback|panic|assert(?:ion)?|fatal|"
    r"segfault|cannot|can't|undefined|not found|denied|timeout|"
    r"exit (?:code|status)|npm ERR!|^\s*E\s{3}\S|^FAILED|^ERROR|"
    r"error\[E\d+\]|^\s*File \".*\", line \d+|\S+\.\w+:\d+(?::\d+)?:",
    re.IGNORECASE | re.MULTILINE,
)
SUMMARY = re.compile(
    r"\d+ (?:passed|failed|errors?|warnings?)|Tests?:|Test Suites:|"
    r"Ran \d+ tests|BUILD (?:SUCCESS|FAILURE)|Finished|Compiling .* in",
    re.IGNORECASE,
)
BASE64 = re.compile(r"[A-Za-z0-9+/=]{1000,}")


def clean(
    text: str,
    cfg: SmartTruncateConfig,
    *,
    is_error: bool = False,
) -> str:
    """Keep head, tail, signal windows and summaries; marker every gap."""
    if "\x00" in text:
        return text
    if len(text.encode("utf-8")) <= cfg.trigger_bytes:
        return text
    ref = sha256(text.encode("utf-8")).hexdigest()[:8]
    lines = [_prepare_line(line, cfg) for line in text.split("\n")]
    head = min(cfg.head_lines, len(lines))
    tail_start = max(0, len(lines) - cfg.tail_lines)
    keep: set[int] = set(range(head)) | set(range(tail_start, len(lines)))

    signal_limit = cfg.max_signal_lines * (2 if is_error else 1)
    signal_seen = 0
    for index, line in enumerate(lines):
        if not (SIGNAL.search(line) or SUMMARY.search(line)):
            continue
        if signal_seen >= signal_limit:
            break
        signal_seen += 1
        for neighbour in range(
            max(0, index - cfg.context_lines),
            min(len(lines), index + cfg.context_lines + 1),
        ):
            keep.add(neighbour)

    output = _render(lines, keep, ref)
    if len(output.encode("utf-8")) > cfg.target_bytes * 1.5:
        keep = {index for index in keep if index < head or index >= tail_start}
        output = _render(lines, keep, ref)
    if len(output.encode("utf-8")) > cfg.target_bytes * 1.5:
        keep = {
            index
            for index in keep
            if index < max(1, head // 2)
            or index >= min(len(lines), len(lines) - max(1, cfg.tail_lines // 2))
        }
        output = _render(lines, keep, ref)
    if len(output.encode("utf-8")) > cfg.target_bytes * 1.5:
        output = output.encode("utf-8")[: int(cfg.target_bytes * 1.5)].decode("utf-8", "ignore")
    return output


def _prepare_line(line: str, cfg: SmartTruncateConfig) -> str:
    if len(line) > cfg.max_line_chars:
        line = line[: cfg.max_line_chars] + f" [ctxproxy: line truncated, {len(line)} chars]"
    return BASE64.sub(lambda match: f"[ctxproxy: base64 blob, {len(match.group(0))} chars]", line)


def _render(lines: list[str], keep: set[int], ref: str) -> str:
    result: list[str] = []
    index = 0
    total = len(lines)
    while index < total:
        if index in keep:
            result.append(lines[index])
            index += 1
            continue
        end = index
        while end < total and end not in keep:
            end += 1
        omitted = end - index
        size_kb = sum(len(lines[i].encode("utf-8")) for i in range(index, end)) / 1024
        result.append(f"[ctxproxy: {omitted} lines ({size_kb:.1f} KB) omitted; ref={ref}]")
        index = end
    return "\n".join(result)


__all__ = ["clean"]
