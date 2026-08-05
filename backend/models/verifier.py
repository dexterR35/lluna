"""Model-file size and SHA-256 verification."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from backend.models.reference.metadata import ExpectedFile


@dataclass(frozen=True)
class VerificationResult:
    valid: bool
    path: Path
    reason: str = ""
    sha256: str = ""


def verify_file(root: str | Path, expected: ExpectedFile) -> VerificationResult:
    base = Path(root).resolve()
    path = (base / expected.relative_path).resolve()
    if base != path and base not in path.parents:
        return VerificationResult(False, path, "Path escapes model root")
    if not path.is_file():
        return VerificationResult(not expected.required, path, "File is missing")
    if expected.size_bytes is not None and path.stat().st_size != expected.size_bytes:
        return VerificationResult(False, path, "File size does not match manifest")
    digest = ""
    if expected.sha256:
        hasher = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(chunk)
        digest = hasher.hexdigest()
        if digest.lower() != expected.sha256.lower():
            return VerificationResult(False, path, "SHA-256 does not match", digest)
    return VerificationResult(True, path, sha256=digest)
