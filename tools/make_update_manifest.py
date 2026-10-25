"""Dev-only signed update-manifest generator.

Example:
    python tools/make_update_manifest.py --artifact dist/ctxproxy-0.3.1.whl \
      --version 0.3.1 --url https://example.com/ctxproxy-0.3.1.whl \
      --private-key key.hex --out dist/manifest.json
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--private-key", required=True, help="hex Ed25519 seed")
    parser.add_argument("--out", type=Path, default=Path("manifest.json"))
    args = parser.parse_args()

    from nacl.signing import SigningKey

    digest = hashlib.sha256(args.artifact.read_bytes()).hexdigest()
    payload = {
        "version": args.version,
        "url": args.url,
        "sha256": digest,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    signing_key = SigningKey(bytes.fromhex(args.private_key))
    payload["signature"] = base64.b64encode(signing_key.sign(canonical).signature).decode()
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")
    print(
        "public key (set update.public_key or CTXPROXY_UPDATE_PUBLIC_KEY): "
        + base64.b64encode(bytes(signing_key.verify_key)).decode()
    )


if __name__ == "__main__":
    main()
