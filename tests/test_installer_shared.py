from __future__ import annotations

import hashlib

import pytest

from backend.tools.installers._shared import sha256_of_file, verify_pinned_artifact


def test_verify_pinned_artifact_accepts_matching_size_and_hash(tmp_path) -> None:
    path = tmp_path / "artifact.bin"
    path.write_bytes(b"hello world")
    digest = hashlib.sha256(b"hello world").hexdigest()

    verify_pinned_artifact(path, expected_size=len(b"hello world"), expected_sha256=digest)


def test_verify_pinned_artifact_rejects_size_mismatch(tmp_path) -> None:
    path = tmp_path / "artifact.bin"
    path.write_bytes(b"hello world")
    digest = hashlib.sha256(b"hello world").hexdigest()

    with pytest.raises(ValueError, match="unexpected size"):
        verify_pinned_artifact(path, expected_size=999, expected_sha256=digest)


def test_verify_pinned_artifact_rejects_hash_mismatch(tmp_path) -> None:
    path = tmp_path / "artifact.bin"
    path.write_bytes(b"hello world")

    with pytest.raises(ValueError, match="SHA-256"):
        verify_pinned_artifact(
            path, expected_size=len(b"hello world"), expected_sha256="0" * 64
        )


def test_sha256_of_file_matches_hashlib(tmp_path) -> None:
    path = tmp_path / "artifact.bin"
    path.write_bytes(b"some binary content" * 1000)

    assert sha256_of_file(path) == hashlib.sha256(path.read_bytes()).hexdigest()
