from __future__ import annotations

from pathlib import Path

from backend.models.dynamic_registry import DynamicModelRecord
from backend.models.reference.manifest import ModelManifest, ModelSource, RuntimeRequirement


def _record(source_type: str, *, installed: bool = False) -> DynamicModelRecord:
    manifest = ModelManifest(
        id="example",
        name="Example",
        task="text-to-image",
        adapter="diffusers",
        source=ModelSource(type=source_type, repo="org/example" if source_type == "huggingface" else "", url="https://example.com/model.safetensors" if source_type == "url" else ""),
        runtime=RuntimeRequirement(profile="diffusers-torch"),
    )
    # Nothing here touches the filesystem; only to_inventory() is inspected.
    return DynamicModelRecord(manifest=manifest, path=Path("models/example"), installed=installed, enabled=False)


def test_can_install_is_true_only_for_huggingface_sourced_models() -> None:
    assert _record("huggingface").to_inventory()["can_install"] is True


def test_can_install_is_false_for_url_sourced_models_since_no_installer_exists() -> None:
    # backend/models/importer.py::install_huggingface rejects anything whose
    # source.type isn't "huggingface", so advertising can_install=True here
    # would promise an install that always fails.
    assert _record("url").to_inventory()["can_install"] is False


def test_can_install_is_false_once_a_model_is_already_installed() -> None:
    assert _record("huggingface", installed=True).to_inventory()["can_install"] is False
