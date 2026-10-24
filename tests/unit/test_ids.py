"""ULID generation, ordering and timestamp recovery."""

from __future__ import annotations

import itertools

import pytest

from ctxproxy.ids import CROCKFORD, new_ulid, ulid_timestamp_ms

# Strictly increasing timestamps keep these tests independent of execution
# order and of the module's monotonic clock state.
_MILLISECONDS = itertools.count(4_000_000_000_000)


def test_ulid_shape_and_charset() -> None:
    value = new_ulid()
    assert len(value) == 26
    assert set(value) <= set(CROCKFORD)


def test_ulid_sorts_by_timestamp() -> None:
    first_ms = next(_MILLISECONDS)
    second_ms = next(_MILLISECONDS)
    early = new_ulid(now_ms=first_ms)
    late = new_ulid(now_ms=second_ms)
    assert early < late
    assert ulid_timestamp_ms(early) == first_ms
    assert ulid_timestamp_ms(late) == second_ms


def test_ulid_is_monotonic_within_a_millisecond() -> None:
    millisecond = next(_MILLISECONDS)
    first = new_ulid(now_ms=millisecond)
    second = new_ulid(now_ms=millisecond)
    assert first < second
    assert ulid_timestamp_ms(first) == ulid_timestamp_ms(second)


def test_ulid_rejects_bad_length() -> None:
    with pytest.raises(ValueError, match="26 characters"):
        ulid_timestamp_ms("too-short")


def test_ulid_rejects_invalid_character() -> None:
    value = new_ulid()
    tampered = "U" + value[1:]
    with pytest.raises(ValueError, match="invalid Crockford"):
        ulid_timestamp_ms(tampered)
