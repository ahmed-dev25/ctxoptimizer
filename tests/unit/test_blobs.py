"""Blob storage for omitted originals."""

from __future__ import annotations

from pathlib import Path

from ctxproxy.telemetry.blobs import BlobStore


def test_put_get_and_prefix(tmp_path: Path) -> None:
    store = BlobStore(tmp_path / "blobs")
    data = b"original tool output"
    ref = store.put(data)
    assert len(ref) == 64
    assert store.get(ref) == data
    assert store.get(ref[:8]) == data
    assert store.count() == 1


def test_unknown_and_ambiguous_refs(tmp_path: Path) -> None:
    store = BlobStore(tmp_path / "blobs")
    assert store.get("deadbeef") is None
    assert store.get("") is None


def test_purge(tmp_path: Path) -> None:
    store = BlobStore(tmp_path / "blobs")
    store.put(b"x")
    store.purge()
    assert store.count() == 0
