#!/usr/bin/env python3
"""Create and Ed25519-sign the canonical manifest for release assets."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
from pathlib import Path

_ASSET = re.compile(
    r"^Lluna-(?P<version>\d+\.\d+\.\d+)-"
    r"(?P<platform>windows|linux|macos)-"
    r"(?P<architecture>x64|arm64)-"
    r"(?P<profile>cpu|cuda|directml|mps)"
    r"\.(?:exe|dmg|tar\.gz)$"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(version: str, assets_dir: Path, base_url: str) -> bytes:
    assets = []
    for path in sorted(assets_dir.iterdir()):
        match = _ASSET.match(path.name)
        if not match or match.group("version") != version:
            continue
        fields = match.groupdict()
        assets.append(
            {
                "name": path.name,
                "platform": fields["platform"],
                "architecture": fields["architecture"],
                "profile": fields["profile"],
                "size": path.stat().st_size,
                "sha256": _sha256(path),
                "url": f"{base_url.rstrip('/')}/{path.name}",
            }
        )
    if not assets:
        raise SystemExit("No correctly named release assets were found.")
    value = {"schema": 1, "version": version, "assets": assets}
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sign_manifest(manifest: bytes, private_key_b64: str) -> str:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    raw = base64.b64decode(private_key_b64, validate=True)
    key = Ed25519PrivateKey.from_private_bytes(raw)
    return base64.b64encode(key.sign(manifest)).decode("ascii")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--assets-dir", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--signature-output", type=Path, required=True)
    parser.add_argument(
        "--private-key-env",
        default="LLUNA_UPDATE_PRIVATE_KEY_B64",
    )
    args = parser.parse_args()
    private_key = os.environ.get(args.private_key_env, "")
    if not private_key:
        raise SystemExit(f"Missing signing key environment: {args.private_key_env}")
    manifest = build_manifest(args.version, args.assets_dir, args.base_url)
    signature = sign_manifest(manifest, private_key)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(manifest)
    args.signature_output.write_text(signature + "\n", encoding="ascii")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
