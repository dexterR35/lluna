"""Signed release-manifest parsing, target selection, and artifact verification."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.core.release_target import ReleaseTarget
from backend.core.update_trust import UPDATE_PUBLIC_KEY_B64


class ManifestVerificationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    platform: str
    architecture: str
    profile: str
    size: int
    sha256: str
    url: str

    @property
    def target_key(self) -> str:
        return f"{self.platform}-{self.architecture}-{self.profile}"


@dataclass(frozen=True)
class ReleaseManifest:
    version: str
    assets: tuple[ReleaseAsset, ...]
    schema: int = 1

    def select(self, target: ReleaseTarget) -> ReleaseAsset:
        matches = [asset for asset in self.assets if asset.target_key == target.key]
        if len(matches) != 1:
            raise ManifestVerificationError(
                f"Release contains {len(matches)} assets for {target.key}; expected one."
            )
        return matches[0]


def canonical_manifest_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def verify_manifest_signature(
    manifest_bytes: bytes,
    signature_b64: str | bytes,
    *,
    public_key_b64: str | None = None,
) -> None:
    public_key_b64 = (
        UPDATE_PUBLIC_KEY_B64 if public_key_b64 is None else public_key_b64
    )
    if not public_key_b64:
        raise ManifestVerificationError(
            "Automatic updates are disabled: no release signing public key is pinned."
        )
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )

        key = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(public_key_b64, validate=True)
        )
        signature = base64.b64decode(signature_b64, validate=True)
        key.verify(signature, manifest_bytes)
    except ManifestVerificationError:
        raise
    except Exception as exc:
        raise ManifestVerificationError(
            "Release manifest signature is invalid."
        ) from exc


def parse_verified_manifest(
    manifest_bytes: bytes,
    signature_b64: str | bytes,
    *,
    public_key_b64: str | None = None,
) -> ReleaseManifest:
    verify_manifest_signature(
        manifest_bytes,
        signature_b64,
        public_key_b64=public_key_b64,
    )
    try:
        value = json.loads(manifest_bytes)
        if canonical_manifest_bytes(value) != manifest_bytes:
            raise ValueError("manifest is not canonical JSON")
        if int(value["schema"]) != 1:
            raise ValueError("unsupported manifest schema")
        assets = tuple(
            ReleaseAsset(
                name=str(item["name"]),
                platform=str(item["platform"]),
                architecture=str(item["architecture"]),
                profile=str(item["profile"]),
                size=int(item["size"]),
                sha256=str(item["sha256"]).lower(),
                url=str(item["url"]),
            )
            for item in value["assets"]
        )
        if not assets or len({asset.name for asset in assets}) != len(assets):
            raise ValueError("manifest assets are empty or duplicated")
        for asset in assets:
            if asset.size <= 0 or len(asset.sha256) != 64:
                raise ValueError(f"invalid metadata for {asset.name}")
        return ReleaseManifest(
            schema=1,
            version=str(value["version"]),
            assets=assets,
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ManifestVerificationError(f"Release manifest is invalid: {exc}") from exc


def verify_artifact(path: str | Path, asset: ReleaseAsset) -> Path:
    artifact = Path(path)
    if not artifact.is_file():
        raise ManifestVerificationError(f"Downloaded update is missing: {artifact}")
    size = artifact.stat().st_size
    if size != asset.size:
        raise ManifestVerificationError(
            f"Downloaded update size mismatch: expected {asset.size}, received {size}."
        )
    digest = hashlib.sha256()
    with artifact.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest().lower() != asset.sha256:
        raise ManifestVerificationError("Downloaded update checksum is invalid.")
    return artifact
