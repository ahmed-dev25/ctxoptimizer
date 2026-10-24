"""Dev-only Ed25519 license signer (SPEC section 19).

Never commit the private key. Example:

    python tools/make_license.py --private-key key.hex --email a@b.c --tier paid
"""

from __future__ import annotations

import argparse
import base64
import json
from datetime import UTC, datetime
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-key", required=True, help="hex Ed25519 seed")
    parser.add_argument("--email", required=True)
    parser.add_argument("--tier", default="paid")
    parser.add_argument("--expires", default=None, help="ISO date/time or omit")
    parser.add_argument("--out", type=Path, default=Path("license.json"))
    args = parser.parse_args()

    from nacl.signing import SigningKey

    seed = bytes.fromhex(args.private_key)
    signing_key = SigningKey(seed)
    payload = {
        "email": args.email,
        "tier": args.tier,
        "issued_at": datetime.now(UTC).isoformat(),
        "expires_at": args.expires,
        "features": ["active_mode"],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    signature = signing_key.sign(canonical).signature
    payload["sig"] = base64.b64encode(signature).decode()
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    public = base64.b64encode(bytes(signing_key.verify_key)).decode()
    print(f"wrote {args.out}")
    print(f"public key (set CTXPROXY_LICENSE_PUBLIC_KEY): {public}")


if __name__ == "__main__":
    main()
