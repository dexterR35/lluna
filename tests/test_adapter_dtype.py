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
        DiffusersAdapter().load(record, dtype="int4")


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
