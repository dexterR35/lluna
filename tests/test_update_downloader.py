from __future__ import annotations

import base64
import hashlib
import json

import pytest

from backend.core.release_target import ReleaseTarget
from backend.updates import downloader
from backend.updates.manifest import canonical_manifest_bytes


def test_release_download_url_rejects_path_injection() -> None:
    with pytest.raises(ValueError):
        downloader.release_download_url("../bad", "asset.exe")
    with pytest.raises(ValueError):
        downloader.release_download_url("1.5.0", "../asset.exe")


def test_prepare_update_downloads_only_signed_matching_target(
    monkeypatch, tmp_path
) -> None:
    crypto = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519")
    serialization = pytest.importorskip("cryptography.hazmat.primitives.serialization")
    target = ReleaseTarget("linux", "x64", "cpu")
    payload = b"release archive"
    name = target.asset_name("1.5.0")
    value = {
        "schema": 1,
        "version": "1.5.0",
        "assets": [
            {
                "name": name,
                "platform": "linux",
                "architecture": "x64",
                "profile": "cpu",
                "size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "url": f"https://example.invalid/{name}",
            }
        ],
    }
    manifest = canonical_manifest_bytes(value)
    private = crypto.Ed25519PrivateKey.generate()
    public = base64.b64encode(
        private.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
    ).decode("ascii")
    signature = base64.b64encode(private.sign(manifest))
    monkeypatch.setattr("backend.updates.manifest.UPDATE_PUBLIC_KEY_B64", public)

    def fetch(url: str) -> bytes:
        return signature if url.endswith(".sig") else manifest

    def download(url, destination, expected_size, progress):
        destination.write_bytes(payload)

    prepared = downloader.prepare_update(
        "1.5.0",
        target=target,
        updates_dir=tmp_path,
        fetch_bytes=fetch,
        download=download,
    )
    assert prepared.path.read_bytes() == payload
    assert prepared.asset.name == name
