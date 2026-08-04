from __future__ import annotations

import base64
import hashlib

import pytest

from backend.core.release_target import ReleaseTarget
from backend.updates.manifest import (
    ManifestVerificationError,
    canonical_manifest_bytes,
    parse_verified_manifest,
    verify_artifact,
)


def _signed_manifest(tmp_path):
    crypto = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519")
    serialization = pytest.importorskip("cryptography.hazmat.primitives.serialization")
    artifact = tmp_path / "Midgard-1.5.0-windows-x64-cpu.exe"
    artifact.write_bytes(b"trusted release")
    value = {
        "schema": 1,
        "version": "1.5.0",
        "assets": [
            {
                "name": artifact.name,
                "platform": "windows",
                "architecture": "x64",
                "profile": "cpu",
                "size": artifact.stat().st_size,
                "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                "url": f"https://example.invalid/{artifact.name}",
            }
        ],
    }
    manifest = canonical_manifest_bytes(value)
    private = crypto.Ed25519PrivateKey.generate()
    public_b64 = base64.b64encode(
        private.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
    ).decode("ascii")
    signature = base64.b64encode(private.sign(manifest)).decode("ascii")
    return artifact, manifest, signature, public_b64


def test_signed_manifest_selects_and_verifies_exact_target(tmp_path) -> None:
    artifact, manifest_bytes, signature, public_key = _signed_manifest(tmp_path)
    manifest = parse_verified_manifest(
        manifest_bytes,
        signature,
        public_key_b64=public_key,
    )
    asset = manifest.select(ReleaseTarget("windows", "x64", "cpu"))
    assert verify_artifact(artifact, asset) == artifact


def test_tampered_manifest_and_artifact_fail_closed(tmp_path) -> None:
    artifact, manifest_bytes, signature, public_key = _signed_manifest(tmp_path)
    with pytest.raises(ManifestVerificationError):
        parse_verified_manifest(
            manifest_bytes.replace(b"1.5.0", b"9.5.0"),
            signature,
            public_key_b64=public_key,
        )

    manifest = parse_verified_manifest(
        manifest_bytes,
        signature,
        public_key_b64=public_key,
    )
    artifact.write_bytes(b"tampered")
    with pytest.raises(ManifestVerificationError):
        verify_artifact(artifact, manifest.assets[0])
