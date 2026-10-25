"""Trailing whitespace and blank-run trimming (SPEC section 12.4)."""

from __future__ import annotations


def clean(text: str, max_blank_run: int = 2) -> str:
    lines = [line.rstrip() for line in text.split("\n")]
    result: list[str] = []
    blanks = 0
    for line in lines:
        if line == "":
            blanks += 1
            if blanks <= max_blank_run:
                result.append(line)
        else:
            blanks = 0
            result.append(line)
    while result and result[-1] == "":
        result.pop()
    if not result:
        return ""
    return "\n".join(result) + "\n"


__all__ = ["clean"]
