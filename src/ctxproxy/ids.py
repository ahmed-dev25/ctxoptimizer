"""Time-sortable ULID identifiers, using only the standard library.

A ULID is 26 characters of Crockford base32: a 48-bit millisecond timestamp
followed by 80 bits of randomness. ULIDs sort lexicographically by creation
time, which keeps request ids cheap to order in SQLite without a separate
counter.
"""

from __future__ import annotations

import os
import threading
import time

CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
ULID_LENGTH = 26
_TIMESTAMP_CHARS = 10
_RANDOM_CHARS = 16
_RANDOM_BITS = 80

_lock = threading.Lock()
_last_ms = 0
_last_random = 0


def new_ulid(*, now_ms: int | None = None) -> str:
    """Return a new ULID, monotonic within a single millisecond.

    Passing ``now_ms`` is intended for tests; production callers omit it.
    """
    global _last_ms, _last_random
    with _lock:
        current = int(time.time() * 1000) if now_ms is None else now_ms
        if current > _last_ms:
            _last_ms = current
            _last_random = int.from_bytes(os.urandom(10), "big")
        else:
            _last_random += 1
            if _last_random >= 1 << _RANDOM_BITS:
                _last_ms += 1
                _last_random = 0
        timestamp = _last_ms
        randomness = _last_random
    return _encode(timestamp, _TIMESTAMP_CHARS) + _encode(randomness, _RANDOM_CHARS)


def ulid_timestamp_ms(value: str) -> int:
    """Return the millisecond timestamp encoded in *value*."""
    if len(value) != ULID_LENGTH:
        raise ValueError(f"ULID must be {ULID_LENGTH} characters, got {len(value)}")
    return _decode(value[:_TIMESTAMP_CHARS])


def _encode(value: int, length: int) -> str:
    digits: list[str] = []
    for _ in range(length):
        digits.append(CROCKFORD[value & 0x1F])
        value >>= 5
    return "".join(reversed(digits))


def _decode(value: str) -> int:
    result = 0
    for char in value:
        try:
            digit = CROCKFORD.index(char)
        except ValueError as exc:
            raise ValueError(f"invalid Crockford base32 character: {char!r}") from exc
        result = (result << 5) | digit
    return result


__all__ = ["CROCKFORD", "ULID_LENGTH", "new_ulid", "ulid_timestamp_ms"]
