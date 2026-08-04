from __future__ import annotations

import sys
import types

import numpy as np
from PIL import Image

from backend.tools.bg_remove import (
    BackgroundRemover,
    apply_protect_mask,
    merge_protect_into_mask,
)
from backend.tools.constant import BgRemoveMode


def test_protect_mask_forces_every_marked_pixel_fully_opaque() -> None:
    model = np.full((5, 6), 40, dtype=np.uint8)
    model[0, 0] = 210
    protect = np.zeros_like(model)
    protect[2, 3] = 1
    protect[3, 4] = 120

    merged = np.asarray(
        merge_protect_into_mask(
            Image.fromarray(model, mode="L"),
            protect,
        )
    )

    assert merged[2, 3] == 255
    assert merged[3, 4] == 255
    assert merged[0, 0] == 210
    assert merged[1, 1] == 40


def test_legacy_protect_merge_restores_source_rgb_and_alpha() -> None:
    cutout = np.zeros((4, 4, 4), dtype=np.uint8)
    cutout[:, :, :3] = (5, 10, 15)
    source = np.full((4, 4, 3), (80, 90, 100), dtype=np.uint8)
    protect = np.zeros((4, 4), dtype=np.uint8)
    protect[1:3, 1:3] = 1

    result = np.asarray(
        apply_protect_mask(
            Image.fromarray(cutout, mode="RGBA"),
            protect,
            source=Image.fromarray(source, mode="RGB"),
        )
    )

    assert np.all(result[1:3, 1:3, 3] == 255)
    assert np.all(result[1:3, 1:3, :3] == (80, 90, 100))
    assert np.all(result[0, 0] == (5, 10, 15, 0))


def test_background_remove_job_applies_saved_keep_mask(monkeypatch, tmp_path) -> None:
    class FakeInner:
        @staticmethod
        def get_providers():
            return ["CPUExecutionProvider"]

    fake_rembg = types.ModuleType("rembg")
    fake_rembg.new_session = lambda *args, **kwargs: types.SimpleNamespace(
        inner_session=FakeInner()
    )
    fake_rembg.remove = lambda image, **kwargs: Image.new("L", image.size, 0)
    monkeypatch.setitem(sys.modules, "rembg", fake_rembg)

    source_path = tmp_path / "source.png"
    output_path = tmp_path / "result.png"
    mask_path = tmp_path / "keep.png"
    Image.new("RGB", (6, 5), (33, 66, 99)).save(source_path)
    keep = np.zeros((5, 6), dtype=np.uint8)
    keep[2, 3] = 1
    Image.fromarray(keep, mode="L").save(mask_path)

    remover = BackgroundRemover(
        BgRemoveMode.BIREFNET,
        providers=["CPUExecutionProvider"],
    )
    remover.process_to_file(
        str(source_path),
        str(output_path),
        protect_mask_path=str(mask_path),
    )
    result = np.asarray(Image.open(output_path).convert("RGBA"))

    assert result[2, 3, 3] == 255
    assert np.all(result[2, 3, :3] == (33, 66, 99))
    assert result[0, 0, 3] == 0


def test_background_remover_retries_cpu_when_accelerated_session_fails(
    monkeypatch,
) -> None:
    calls = []

    class FakeInner:
        @staticmethod
        def get_providers():
            return ["CPUExecutionProvider"]

    def new_session(*args, **kwargs):
        providers = kwargs["providers"]
        calls.append(providers)
        if providers != ["CPUExecutionProvider"]:
            raise RuntimeError("CUDA provider DLL is unavailable")
        return types.SimpleNamespace(inner_session=FakeInner())

    fake_rembg = types.ModuleType("rembg")
    fake_rembg.new_session = new_session
    monkeypatch.setitem(sys.modules, "rembg", fake_rembg)

    remover = BackgroundRemover(
        BgRemoveMode.BIREFNET,
        providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
    )
    remover._ensure_session()

    assert calls == [
        ["CUDAExecutionProvider", "CPUExecutionProvider"],
        ["CPUExecutionProvider"],
    ]
    assert remover.device_label == "CPU"


def test_background_remover_logs_provider_after_session_initializes(
    monkeypatch,
    tmp_path,
) -> None:
    class FakeInner:
        @staticmethod
        def get_providers():
            return ["CUDAExecutionProvider", "CPUExecutionProvider"]

    fake_rembg = types.ModuleType("rembg")
    fake_rembg.new_session = lambda *args, **kwargs: types.SimpleNamespace(
        inner_session=FakeInner()
    )
    fake_rembg.remove = lambda image, **kwargs: Image.new("L", image.size, 255)
    monkeypatch.setitem(sys.modules, "rembg", fake_rembg)

    source_path = tmp_path / "source.png"
    output_path = tmp_path / "result.png"
    Image.new("RGB", (4, 3), (20, 40, 60)).save(source_path)
    logs: list[str] = []

    remover = BackgroundRemover(
        BgRemoveMode.BIREFNET,
        providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
    )
    remover.process_to_file(
        str(source_path),
        str(output_path),
        log=logs.append,
    )

    assert logs[0] == "Device: GPU (CUDA) | Model: birefnet-general"
    assert remover.device_label == "GPU (CUDA)"
