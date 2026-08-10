"""Model installed, runtime installed and hardware compatible are separate facts."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.models.dynamic_registry import DynamicModelRecord, _path_stamp
from backend.models.reference import runtimes
from backend.models.reference.manifest import (
    MANIFEST_FILENAME,
    ModelManifest,
    ModelSource,
    RuntimeRequirement,
)


def _manifest(profile: str = "diffusers-torch") -> ModelManifest:
    return ModelManifest(
        id="example",
        name="Example",
        task="text-to-image",
        adapter="diffusers",
        source=ModelSource(type="huggingface", repo="org/example"),
        runtime=RuntimeRequirement(profile=profile),
    )


@pytest.fixture
def runtime_installed(monkeypatch):
    def apply(installed: bool):
        monkeypatch.setattr(runtimes, "runtime_installed", lambda profile: installed)

    return apply


@pytest.fixture
def configured(monkeypatch):
    """Isolate the runtime question from the unrelated 'needs configuration' gate."""
    monkeypatch.setattr(ModelManifest, "is_configured", lambda self: True)


def test_missing_runtime_keeps_the_model_compatible_but_not_runnable(runtime_installed):
    """Install flows need 'compatible'; execution needs 'runnable'."""
    runtime_installed(False)

    status = runtimes.runtime_status(_manifest())

    assert status["compatible"] is True
    assert status["installed"] is False
    assert status["runnable"] is False


def test_present_runtime_is_runnable(runtime_installed):
    runtime_installed(True)

    assert runtimes.runtime_status(_manifest())["runnable"] is True


def test_model_cannot_be_enabled_while_its_runtime_is_missing(
    runtime_installed, configured, tmp_path
):
    """Otherwise the model reports enabled and then fails on first use."""
    runtime_installed(False)
    record = DynamicModelRecord(
        manifest=_manifest(), path=tmp_path, installed=True, enabled=True
    )

    inventory = record.to_inventory()

    assert inventory["enabled"] is False
    assert inventory["can_toggle"] is False
    assert inventory["runtime_installed"] is False


def test_model_with_its_runtime_present_can_be_enabled(runtime_installed, configured, tmp_path):
    runtime_installed(True)
    record = DynamicModelRecord(
        manifest=_manifest(), path=tmp_path, installed=True, enabled=True
    )

    inventory = record.to_inventory()

    assert inventory["enabled"] is True
    assert inventory["runtime_installed"] is True


def _model_dir(tmp_path: Path) -> Path:
    path = tmp_path / "custom-model"
    path.mkdir()
    (path / MANIFEST_FILENAME).write_text("{}", encoding="utf-8")
    (path / "model.safetensors").write_bytes(b"original weights")
    return path


def test_replacing_undeclared_weights_moves_the_stamp(tmp_path):
    """A manifest with an incomplete expected_files list must not hide a swap."""
    path = _model_dir(tmp_path)
    before = _path_stamp(path, ())

    (path / "model.safetensors").write_bytes(b"different weights!")
    after = _path_stamp(path, ())

    assert before != after


def test_same_size_in_place_overwrite_still_moves_the_stamp(tmp_path):
    """Directory mtime does not change on in-place writes, so size alone is not enough."""
    path = _model_dir(tmp_path)
    weights = path / "model.safetensors"
    before = _path_stamp(path, ())

    stat = weights.stat()
    weights.write_bytes(b"REPLACED weights")  # identical length
    assert weights.stat().st_size == stat.st_size
    after = _path_stamp(path, ())

    assert before != after


def test_untouched_model_keeps_a_stable_stamp(tmp_path):
    path = _model_dir(tmp_path)

    assert _path_stamp(path, ()) == _path_stamp(path, ())
