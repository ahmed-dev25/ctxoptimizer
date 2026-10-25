"""Content-addressed blob storage for omitted/duplicated originals (SPEC 12.13)."""

from __future__ import annotations

import os
import shutil
import zlib
from hashlib import sha256
from pathlib import Path


class BlobStore:
    """zlib-compressed files named by sha256; supports short-ref lookup."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, data: bytes) -> str:
        digest = sha256(data).hexdigest()
        path = self._path(digest)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(zlib.compress(data, 6))
            if os.name == "posix":
                os.chmod(path, 0o600)
        return digest

    def get(self, ref: str) -> bytes | None:
        if not ref:
            return None
        if len(ref) >= 64:
            path = self._path(ref)
        else:
            matches = sorted(self.root.glob(f"*/{ref}*"))
            if len(matches) != 1:
                return None
            path = matches[0]
        if not path.is_file():
            return None
        try:
            return zlib.decompress(path.read_bytes())
        except zlib.error:
            return None

    def purge(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True, exist_ok=True)

    def count(self) -> int:
        return sum(1 for _ in self.root.glob("*/*"))

    def _path(self, digest: str) -> Path:
        return self.root / digest[:2] / digest


__all__ = ["BlobStore"]
