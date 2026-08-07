from __future__ import annotations

from pathlib import Path

from backend.core.paths import AppPaths
from backend.models.dynamic_registry import DynamicModelRegistry
from backend.models.importer import register_huggingface
from backend.models.service import generation_minimum_vram_mb


def _paths(root: Path) -> AppPaths:
    config = root / "config"
    return AppPaths(
        project_root=root,
        config_dir=config,
        data_dir=root,
        updates_dir=root / "updates",
        config_file=config / "config.json",
        runtime_config_file=config / "runtime.json",
        shipped_config_file=config / "defaults.json",
        models_dir=root / "models",
        runtime_file=root / "lluna_runtime.json",
    )


def test_builtin_generate_modes_resolve_to_catalog_minimums():
    # Klein/base variants fall back to the generic "flux" catalog entry.
    assert generation_minimum_vram_mb("FLUX.2-klein-base-4B") == 12000
    assert generation_minimum_vram_mb("FLUX.2-klein-9B") == 12000
    # Explicitly mapped entries use their own declared minimum.
    assert generation_minimum_vram_mb("FLUX.2-dev") == 12000
    assert generation_minimum_vram_mb("FLUX.2-klein-9b-fp8") == 10000
    assert generation_minimum_vram_mb("Qwen-Image") == 12000


def test_unknown_or_missing_model_value_resolves_to_zero():
    assert generation_minimum_vram_mb("not-a-real-mode") == 0
    assert generation_minimum_vram_mb("custom:does-not-exist") == 0


def test_custom_model_reads_declared_minimum_from_its_manifest(tmp_path, monkeypatch):
    registry = DynamicModelRegistry(_paths(tmp_path))
    monkeypatch.setattr(DynamicModelRegistry, "_instance", registry)

    raw = {
        "schema": 1,
        "id": "my-custom-flux",
        "name": "My Custom FLUX",
        "description": "test",
        "task": "text-to-image",
        "adapter": "diffusers",
        "source": {"type": "huggingface", "repo": "someone/some-flux-model"},
        "runtime": {"profile": "diffusers-torch"},
        "hardware": {"backends": ["cuda"], "minimumVramMb": 16000},
        "security": {"trustRemoteCode": False, "allowPickle": False},
        "variant": {"kind": "base"},
        "capabilities": {
            "provenance": "reviewed-manifest",
            "tasks": ["text-to-image"],
            "inputs": ["prompt"],
            "outputs": ["image"],
            "dtypes": ["bf16"],
            "steps": {"default": 20, "minimum": 1, "maximum": 50},
            "guidance": True,
            "guidanceScale": {"default": 4.0, "minimum": 0, "maximum": 20},
            "negativePrompt": True,
            "seed": True,
            "supportedWidths": [1024],
            "supportedHeights": [1024],
        },
        "expectedFiles": ["model_index.json", "transformer/model.safetensors"],
    }
    register_huggingface(raw)

    assert generation_minimum_vram_mb("custom:my-custom-flux") == 16000
