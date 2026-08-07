"""Precision (dtype) selection for custom-model adapters."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import pytest

from backend.models.adapters import (
    AdapterError,
    DiffusersAdapter,
    DynamicRuntimeManager,
    RuntimeAdapter,
)
from backend.models.dynamic_registry import DynamicModelRecord, DynamicModelRegistry
from backend.models.reference.manifest import ModelManifest


def _diffusers_manifest(*, dtypes: list[str], backends: list[str] | None = None) -> ModelManifest:
    return ModelManifest.from_mapping(
        {
            "schema": 1,
            "id": "custom-image",
            "name": "Custom Image",
            "task": "text-to-image",
            "adapter": "diffusers",
            "source": {"type": "local", "localName": "custom-image"},
            "runtime": {"profile": "diffusers-torch"},
            "hardware": {"backends": backends or ["cpu", "cuda", "mps"]},
            "security": {},
            "variant": {"kind": "distilled"},
            "capabilities": {
                "provenance": "reviewed-manifest",
                "tasks": ["text-to-image"],
                "inputs": ["prompt"],
                "outputs": ["image"],
                "seed": True,
                "steps": {"default": 4, "minimum": 1, "maximum": 8},
                "supportedWidths": [512, 768, 1024],
                "supportedHeights": [512, 768, 1024],
                "dtypes": dtypes,
            },
        }
    )


class _FakePipeline:
    def to(self, _device: str) -> "_FakePipeline":
        return self


def _install_fake_diffusers(monkeypatch: pytest.MonkeyPatch, calls: list[dict[str, Any]]) -> None:
    module = types.ModuleType("diffusers")

    class _FakeDiffusionPipeline:
        @staticmethod
        def from_pretrained(path: str, **kwargs: Any) -> _FakePipeline:
            calls.append({"path": path, **kwargs})
            return _FakePipeline()

    module.DiffusionPipeline = _FakeDiffusionPipeline
    monkeypatch.setitem(sys.modules, "diffusers", module)


def _record(manifest: ModelManifest) -> DynamicModelRecord:
    return DynamicModelRecord(manifest=manifest, path=Path("/fake/custom-image"), installed=True, enabled=True)


def test_explicit_dtype_is_loaded_when_declared_supported(monkeypatch: pytest.MonkeyPatch) -> None:
    import torch

    calls: list[dict[str, Any]] = []
    _install_fake_diffusers(monkeypatch, calls)
    record = _record(_diffusers_manifest(dtypes=["fp32"]))

    DiffusersAdapter().load(record, dtype="fp32")

    assert calls[0]["torch_dtype"] == torch.float32


def test_unknown_dtype_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_diffusers(monkeypatch, [])
    record = _record(_diffusers_manifest(dtypes=["fp32"]))

    with pytest.raises(AdapterError, match="Unknown precision"):
        DiffusersAdapter().load(record, dtype="int2")


def test_dtype_not_declared_by_manifest_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_diffusers(monkeypatch, [])
    record = _record(_diffusers_manifest(dtypes=["fp32"]))

    with pytest.raises(AdapterError, match="only declares support for"):
        DiffusersAdapter().load(record, dtype="fp16")


def test_cuda_only_dtype_is_rejected_without_cuda(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_diffusers(monkeypatch, [])
    record = _record(_diffusers_manifest(dtypes=["bf16"]))

    with pytest.raises(AdapterError, match="requires CUDA"):
        DiffusersAdapter().load(record, dtype="bf16")


def test_auto_falls_back_to_the_only_declared_dtype(monkeypatch: pytest.MonkeyPatch) -> None:
    import torch

    calls: list[dict[str, Any]] = []
    _install_fake_diffusers(monkeypatch, calls)
    record = _record(_diffusers_manifest(dtypes=["fp32"]))

    DiffusersAdapter().load(record, dtype=None)

    assert calls[0]["torch_dtype"] == torch.float32


def test_device_incompatible_with_manifest_backends_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_diffusers(monkeypatch, [])
    record = _record(_diffusers_manifest(dtypes=["fp32"], backends=["cuda"]))

    with pytest.raises(AdapterError, match="not cpu"):
        DiffusersAdapter().load(record, dtype="fp32")


def _install_fake_diffusers_with_quant(monkeypatch: pytest.MonkeyPatch, calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    quant_configs: list[dict[str, Any]] = []
    module = types.ModuleType("diffusers")

    class _FakeDiffusionPipeline:
        @staticmethod
        def from_pretrained(path: str, **kwargs: Any) -> _FakePipeline:
            calls.append({"path": path, **kwargs})
            return _FakePipeline()

    class _FakePipelineQuantizationConfig:
        def __init__(self, *, quant_backend: str, quant_kwargs: dict, components_to_quantize: list[str]) -> None:
            quant_configs.append(
                {
                    "quant_backend": quant_backend,
                    "quant_kwargs": quant_kwargs,
                    "components_to_quantize": components_to_quantize,
                }
            )

    module.DiffusionPipeline = _FakeDiffusionPipeline
    module.PipelineQuantizationConfig = _FakePipelineQuantizationConfig
    monkeypatch.setitem(sys.modules, "diffusers", module)
    return quant_configs


def _force_cuda(monkeypatch: pytest.MonkeyPatch) -> None:
    import torch

    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(torch.cuda, "is_bf16_supported", lambda: True)


def _write_model_index(path: Path, components: dict[str, Any]) -> None:
    import json

    path.mkdir(parents=True, exist_ok=True)
    (path / "model_index.json").write_text(
        json.dumps({"_class_name": "FakePipeline", **components}), encoding="utf-8"
    )


def test_int4_quantization_loads_when_declared_and_available(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import torch

    import backend.models.adapters as adapters_module

    _force_cuda(monkeypatch)
    monkeypatch.setattr(adapters_module, "_bitsandbytes_available", lambda: True)
    _write_model_index(tmp_path, {"transformer": ["pkg", "Cls"], "vae": ["pkg", "Cls"]})
    calls: list[dict[str, Any]] = []
    quant_configs = _install_fake_diffusers_with_quant(monkeypatch, calls)
    manifest = _diffusers_manifest(dtypes=["int4"])
    record = DynamicModelRecord(manifest=manifest, path=tmp_path, installed=True, enabled=True)

    DiffusersAdapter().load(record, dtype="int4")

    assert calls[0]["torch_dtype"] == torch.bfloat16
    assert quant_configs == [
        {
            "quant_backend": "bitsandbytes_4bit",
            "quant_kwargs": {
                "load_in_4bit": True,
                "bnb_4bit_quant_type": "nf4",
                "bnb_4bit_compute_dtype": torch.bfloat16,
            },
            "components_to_quantize": ["transformer"],
        }
    ]


def test_int8_quantization_requires_cuda(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_model_index(tmp_path, {"transformer": ["pkg", "Cls"]})
    _install_fake_diffusers_with_quant(monkeypatch, [])
    manifest = _diffusers_manifest(dtypes=["int8"])
    record = DynamicModelRecord(manifest=manifest, path=tmp_path, installed=True, enabled=True)

    with pytest.raises(AdapterError, match="requires CUDA"):
        DiffusersAdapter().load(record, dtype="int8")


def test_quantization_requires_bitsandbytes_installed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.models.adapters as adapters_module

    _force_cuda(monkeypatch)
    monkeypatch.setattr(adapters_module, "_bitsandbytes_available", lambda: False)
    _write_model_index(tmp_path, {"transformer": ["pkg", "Cls"]})
    _install_fake_diffusers_with_quant(monkeypatch, [])
    manifest = _diffusers_manifest(dtypes=["int8"])
    record = DynamicModelRecord(manifest=manifest, path=tmp_path, installed=True, enabled=True)

    with pytest.raises(AdapterError, match="bitsandbytes package"):
        DiffusersAdapter().load(record, dtype="int8")


def test_quantization_requires_declared_manifest_support(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.models.adapters as adapters_module

    _force_cuda(monkeypatch)
    monkeypatch.setattr(adapters_module, "_bitsandbytes_available", lambda: True)
    _write_model_index(tmp_path, {"transformer": ["pkg", "Cls"]})
    _install_fake_diffusers_with_quant(monkeypatch, [])
    manifest = _diffusers_manifest(dtypes=["fp32"])
    record = DynamicModelRecord(manifest=manifest, path=tmp_path, installed=True, enabled=True)

    with pytest.raises(AdapterError, match="only declares support for"):
        DiffusersAdapter().load(record, dtype="int8")


def test_quantization_requires_a_quantizable_component(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.models.adapters as adapters_module

    _force_cuda(monkeypatch)
    monkeypatch.setattr(adapters_module, "_bitsandbytes_available", lambda: True)
    _write_model_index(tmp_path, {"vae": ["pkg", "Cls"], "scheduler": ["pkg", "Cls"]})
    _install_fake_diffusers_with_quant(monkeypatch, [])
    manifest = _diffusers_manifest(dtypes=["int8"])
    record = DynamicModelRecord(manifest=manifest, path=tmp_path, installed=True, enabled=True)

    with pytest.raises(AdapterError, match="quantizable component"):
        DiffusersAdapter().load(record, dtype="int8")


def test_auto_never_selects_a_quantized_dtype(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_model_index(tmp_path, {"transformer": ["pkg", "Cls"]})
    _install_fake_diffusers_with_quant(monkeypatch, [])
    manifest = _diffusers_manifest(dtypes=["int4"])
    record = DynamicModelRecord(manifest=manifest, path=tmp_path, installed=True, enabled=True)

    with pytest.raises(AdapterError, match="No declared dtype"):
        DiffusersAdapter().load(record, dtype=None)


class _RecordingAdapter(RuntimeAdapter):
    id = "transformers"

    def __init__(self) -> None:
        self.load_calls: list[str | None] = []

    def load(self, record: DynamicModelRecord, *, dtype: str | None = None) -> Any:
        self.load_calls.append(dtype)
        return object()

    def run(self, loaded: Any, inputs: dict, *, progress=None, cancel_event=None) -> Any:
        return "ok"


class _StubRegistry:
    def __init__(self, record: DynamicModelRecord) -> None:
        self._record = record

    def get(self, _model_id: str) -> DynamicModelRecord:
        return self._record


def _transformers_manifest() -> ModelManifest:
    return ModelManifest.from_mapping(
        {
            "schema": 1,
            "id": "custom-restore",
            "name": "Custom Restore",
            "task": "image-restoration",
            "adapter": "transformers",
            "source": {"type": "local", "localName": "custom-restore"},
            "runtime": {"profile": "transformers-torch"},
            "hardware": {"backends": ["cpu", "cuda", "mps"]},
            "security": {},
            "variant": {"kind": "base"},
            "capabilities": {
                "provenance": "reviewed-manifest",
                "tasks": ["image-restoration"],
                "inputs": ["image"],
                "outputs": ["image"],
                "dtypes": ["fp32"],
            },
        }
    )


def test_runtime_manager_cache_key_is_dtype_aware(monkeypatch: pytest.MonkeyPatch) -> None:
    record = _record(_transformers_manifest())
    monkeypatch.setattr(DynamicModelRegistry, "_instance", _StubRegistry(record))
    monkeypatch.setattr(
        "backend.models.reference.runtimes.runtime_status",
        lambda _manifest: {"compatible": True, "reasons": []},
    )
    fake_adapter = _RecordingAdapter()
    monkeypatch.setitem(sys.modules, "backend.models.adapters", sys.modules["backend.models.adapters"])
    monkeypatch.setattr("backend.models.adapters.ADAPTERS", {"transformers": fake_adapter})

    manager = DynamicRuntimeManager(cache_size=2)
    manager.run("custom-restore", {"input": "x"}, dtype="fp16")
    manager.run("custom-restore", {"input": "x"}, dtype="fp16")
    manager.run("custom-restore", {"input": "x"}, dtype="fp32")

    assert fake_adapter.load_calls == ["fp16", "fp32"]
