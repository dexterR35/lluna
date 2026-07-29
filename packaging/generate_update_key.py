#!/usr/bin/env python3
"""Generate the one-time Ed25519 key pair used for Midgard release manifests."""

from __future__ import annotations

import argparse
import base64
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--private-output",
        type=Path,
        required=True,
        help="Local file for the base64 private key; never commit this file.",
    )
    args = parser.parse_args()
    if args.private_output.exists():
        raise SystemExit(f"Refusing to overwrite {args.private_output}")
    private = Ed25519PrivateKey.generate()
    private_raw = private.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public_raw = private.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    args.private_output.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        args.private_output,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    with os.fdopen(descriptor, "w", encoding="ascii") as stream:
        stream.write(base64.b64encode(private_raw).decode("ascii") + "\n")
    print("Public key for backend/core/update_trust.py:")
    print(base64.b64encode(public_raw).decode("ascii"))
    print(f"Private key written to {args.private_output}")
    print("Store its value as GitHub secret MIDGARD_UPDATE_PRIVATE_KEY_B64.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
