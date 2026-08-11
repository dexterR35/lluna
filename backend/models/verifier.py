"""Model-file size and SHA-256 verification."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.artifacts.hashing import hash_file
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
        digest = hash_file(path)
        if digest.lower() != expected.sha256.lower():
            return VerificationResult(False, path, "SHA-256 does not match", digest)
    return VerificationResult(True, path, sha256=digest)
