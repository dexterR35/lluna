"""Fail-closed verification and atomic promotion for downloaded model files."""

from __future__ import annotations

import os
from pathlib import Path

from backend.models.metadata import ExpectedFile
from backend.models.verifier import VerificationResult, verify_file


class ArtifactVerificationError(RuntimeError):
    """A staged model artifact did not match its reviewed manifest."""


def _validate_integrity_metadata(expected: ExpectedFile) -> None:
    if expected.size_bytes is None or not expected.sha256:
        raise ArtifactVerificationError(
            "Model artifact manifest must declare size and SHA-256"
        )
    digest = expected.sha256.lower()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ArtifactVerificationError(
            "Model artifact manifest contains an invalid SHA-256"
        )


def promote_verified_artifact(
    partial_path: str | Path,
    destination: str | Path,
    expected: ExpectedFile,
) -> VerificationResult:
    """Verify a staged file and atomically replace the final artifact.

    The existing destination is left untouched when verification fails.
    Callers retain ownership of failed partial files and may quarantine or
    remove them according to their download lifecycle.
    """
    _validate_integrity_metadata(expected)
    partial = Path(partial_path)
    final = Path(destination)
    if partial.parent.resolve() != final.parent.resolve():
        raise ArtifactVerificationError(
            "Staged and final model artifacts must share a directory"
        )
    if Path(expected.relative_path).name != final.name:
        raise ArtifactVerificationError(
            "Model artifact destination does not match manifest"
        )

    staged_expected = ExpectedFile(
        relative_path=partial.name,
        size_bytes=expected.size_bytes,
        sha256=expected.sha256,
        required=expected.required,
    )
    result = verify_file(partial.parent, staged_expected)
    if not result.valid:
        raise ArtifactVerificationError(result.reason or "Artifact verification failed")

    final.parent.mkdir(parents=True, exist_ok=True)
    os.replace(partial, final)
    return result
