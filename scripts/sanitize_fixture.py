"""Scrub common local identifiers from JSON fixtures before committing them."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_PATTERNS = (
    (re.compile(r"[A-Za-z]:\\Users\\[^\\\"']+"), r"C:\\Users\\user"),
    (re.compile(r"/home/[^/\"']+"), "/home/user"),
    (re.compile(r"/Users/[^/\"']+"), "/Users/user"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "user@example.com"),
)


def scrub(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def main(paths: list[str]) -> None:
    for raw in paths:
        path = Path(raw)
        payload = json.loads(path.read_text(encoding="utf-8"))
        cleaned = scrub(json.dumps(payload, indent=2)) + "\n"
        path.write_text(cleaned, encoding="utf-8")
        print(f"sanitized {path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("usage: sanitize_fixture.py <request.json> [...]")
    main(sys.argv[1:])
