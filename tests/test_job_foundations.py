from __future__ import annotations

from pathlib import Path

import pytest

from backend.application.jobs import JobPhase, JobStatus
from backend.diagnostics.redaction import redact_text, redact_url
from backend.media.output_paths import default_output_path, next_available_path
from backend.media.progress import CancellationToken
from backend.media.workspace import JobWorkspace
from backend.tools.infer_protocol import JobRequest, JobType


def test_job_status_validates_progress() -> None:
    status = JobStatus("1", "enhance", JobPhase.PROCESSING, 50)
    assert status.phase.terminal is False
    assert JobPhase.COMPLETED.terminal is True
    with pytest.raises(ValueError):
        JobStatus("1", "enhance", JobPhase.PROCESSING, 101)


def test_typed_request_preserves_legacy_wire_format() -> None:
    message, payload = JobRequest(7, JobType.ENHANCE, {"input_path": "x"}).to_wire()
    assert message == "START_JOB"
    assert payload["run_id"] == 7
    assert payload["job_type"] == "enhance"


def test_output_path_and_collision(tmp_path: Path) -> None:
    source = tmp_path / "photo.png"
    source.touch()
    output = default_output_path(source, suffix="_upscale")
    assert output == tmp_path / "photo_upscale.png"
    output.touch()
    assert next_available_path(output) == tmp_path / "photo_upscale-1.png"


def test_workspace_cleanup_and_path_safety() -> None:
    workspace = JobWorkspace.create("test")
    path = workspace.new_path("../result", ".tmp")
    path.write_text("temporary", encoding="utf-8")
    root = workspace.path
    assert path.parent == root
    workspace.close()
    assert not root.exists()


def test_cancellation_token() -> None:
    token = CancellationToken()
    token.cancel()
    with pytest.raises(RuntimeError):
        token.raise_if_cancelled()


def test_diagnostic_redaction() -> None:
    assert "hf_secretvalue" not in redact_text("token=hf_secretvalue")
    assert redact_url("https://user:pass@example.test/file?q=secret") == (
        "https://example.test/file"
    )
