from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.application.preflight import (
    validate_packaged_runtime,
    validate_python_runtime,
)
from backend.core.release_target import ReleaseTarget
from backend.diagnostics.errors import DependencyError


def _packaged_paths(tmp_path):
    root = tmp_path / "bundle"
    required = (
        root / "backend/interface/en.ini",
        root / "backend/ffmpeg/linux_x64/ffmpeg",
        root / "backend/models/V5/ch_det/inference.pdiparams",
        root / "backend/models/V5/ch_det_fast/inference.pdiparams",
        root / "backend/models/sttn-auto/infer_model.pth",
        root / "backend/models/sttn-det/sttn.pth",
        root / "backend/models/big-lama/fs_manifest.csv",
        root / "backend/models/propainter/fs_manifest.csv",
    )
    for path in required:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"present")
    return SimpleNamespace(
        project_root=root,
        translation_file=root / "backend/interface/en.ini",
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        models_dir=tmp_path / "data/models",
        updates_dir=tmp_path / "data/updates",
    )


def test_packaged_preflight_checks_embedded_runtime_and_writes_log(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys.version_info", (3, 12, 0, "final", 0))
    paths = _packaged_paths(tmp_path)
    report = validate_packaged_runtime(
        paths,
        target=ReleaseTarget("linux", "x64", "cpu"),
    )
    assert report is not None
    assert report.log_file.is_file()
    text = report.log_file.read_text(encoding="utf-8")
    assert "embedded=true" in text
    assert "target=linux-x64-cpu" in text


def test_packaged_preflight_fails_when_release_resource_is_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("sys.frozen", True, raising=False)
    paths = _packaged_paths(tmp_path)
    paths.translation_file.unlink()
    with pytest.raises(DependencyError, match="missing packaged resources"):
        validate_packaged_runtime(
            paths,
            target=ReleaseTarget("linux", "x64", "cpu"),
        )


def test_python_runtime_rejects_other_minor_versions(monkeypatch) -> None:
    monkeypatch.setattr("sys.version_info", (3, 14, 0, "final", 0))
    with pytest.raises(DependencyError, match="requires 64-bit Python 3.12"):
        validate_python_runtime()
