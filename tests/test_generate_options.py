from __future__ import annotations

import pytest

from backend.tools.constant import GenerateMode
from backend.tools.generate_models import (
    MODEL_CATALOG,
    _validate_download_snapshot,
    catalog_info,
    model_downloads,
)
from backend.tools.generate_options import (
    default_size_preset_for_mode,
    default_step_preset_for_mode,
    resolve_guidance,
    size_presets_for_mode,
    step_presets_for_mode,
    validate_steps_for_mode,
)


@pytest.mark.parametrize(
    ("mode", "steps", "default_steps", "guidance"),
    [
        (GenerateMode.FLUX2_KLEIN_4B, [4], 4, 1.0),
        (GenerateMode.FLUX2_KLEIN_9B, [4], 4, 1.0),
        (GenerateMode.FLUX2_KLEIN_BASE_4B, [50], 50, 4.0),
        (GenerateMode.FLUX2_KLEIN_BASE_9B, [50], 50, 4.0),
        (GenerateMode.FLUX2_DEV, [50], 50, 4.0),
        (GenerateMode.FLUX2_KLEIN_9B_FP8, [4], 4, 1.0),
        (GenerateMode.QWEN_IMAGE, [50], 50, 4.0),
    ],
)
def test_each_generate_model_has_its_own_step_profile(
    mode: GenerateMode,
    steps: list[int],
    default_steps: int,
    guidance: float,
) -> None:
    assert [preset.steps for preset in step_presets_for_mode(mode)] == steps
    assert default_step_preset_for_mode(mode).steps == default_steps
    assert resolve_guidance(mode) == guidance


def test_every_generate_mode_is_in_the_install_catalog() -> None:
    assert {info.mode for info in MODEL_CATALOG} == set(GenerateMode)
    assert [info.mode for info in MODEL_CATALOG if info.is_default] == [
        GenerateMode.FLUX2_KLEIN_BASE_4B
    ]


def test_incompatible_step_count_is_rejected() -> None:
    with pytest.raises(ValueError, match="configured step preset"):
        validate_steps_for_mode(GenerateMode.FLUX2_KLEIN_4B, 50)
    assert validate_steps_for_mode(GenerateMode.FLUX2_KLEIN_4B, 4) == 4
    with pytest.raises(ValueError, match="configured step preset"):
        validate_steps_for_mode(GenerateMode.FLUX2_KLEIN_BASE_4B, 100)
    assert validate_steps_for_mode(GenerateMode.FLUX2_KLEIN_BASE_4B, 50) == 50


def test_model_specific_size_defaults() -> None:
    for mode in GenerateMode:
        assert default_size_preset_for_mode(mode).width == 1024
        assert [(preset.width, preset.height) for preset in size_presets_for_mode(mode)] == [
            (512, 512),
            (768, 768),
            (1024, 1024),
        ]


def test_generate_downloads_keep_only_one_runtime_weight_layout() -> None:
    for info in MODEL_CATALOG:
        patterns = "\n".join(
            pattern for download in model_downloads(info) for pattern in download.allow_patterns
        )
        assert ".bin" not in patterns
        assert ".ckpt" not in patterns
        assert "safety_checker" not in patterns
        assert "onnx" not in patterns
        assert "non_ema" not in patterns

    flux = catalog_info(GenerateMode.FLUX2_KLEIN_BASE_4B)
    assert flux is not None
    assert "transformer/*.safetensors" in flux.download_allow_patterns
    assert "*.safetensors" not in flux.download_allow_patterns

    fp8 = catalog_info(GenerateMode.FLUX2_KLEIN_9B_FP8)
    assert fp8 is not None
    downloads = model_downloads(fp8)
    assert [download.hf_repo for download in downloads] == [
        "black-forest-labs/FLUX.2-klein-9b-fp8",
        "black-forest-labs/FLUX.2-klein-9B",
    ]
    assert fp8.download_allow_patterns == ("flux-2-klein-9b-fp8.safetensors",)
    assert "transformer/*.safetensors" not in downloads[1].allow_patterns
    assert "transformer/config.json" in downloads[1].allow_patterns


@pytest.mark.parametrize("mode", list(GenerateMode))
def test_filtered_generate_snapshot_is_checked_before_install(
    tmp_path,
    mode: GenerateMode,
) -> None:
    info = catalog_info(mode)
    assert info is not None

    required = [
        "model_index.json",
        "scheduler/scheduler_config.json",
        "text_encoder/config.json",
        "text_encoder/model.fp16.safetensors",
        "tokenizer/tokenizer_config.json",
        "vae/config.json",
        "vae/diffusion_pytorch_model.fp16.safetensors",
    ]
    required.append("transformer/config.json")
    if info.single_file_name:
        required.append(info.single_file_name)
    else:
        required.append("transformer/diffusion_pytorch_model.safetensors")

    for relative in required:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    _validate_download_snapshot(info, tmp_path)
    (tmp_path / "vae/diffusion_pytorch_model.fp16.safetensors").unlink()
    with pytest.raises(RuntimeError, match=r"vae/\*\.safetensors"):
        _validate_download_snapshot(info, tmp_path)


def test_qwen_generation_uses_true_cfg_and_an_empty_negative_prompt() -> None:
    from backend.tools.image_generate import _QwenImageRunner

    runner = object.__new__(_QwenImageRunner)
    kwargs = runner._build_call_kwargs(
        prompt="Text rendered in an image",
        width=1024,
        height=1024,
        steps=50,
        guidance=4.0,
        generator=None,
    )
    assert kwargs["true_cfg_scale"] == 4.0
    assert kwargs["negative_prompt"] == " "
    assert "guidance_scale" not in kwargs


def test_fp8_loader_combines_single_file_with_local_diffusers_components(
    tmp_path, monkeypatch
) -> None:
    import torch

    from backend.tools import image_generate

    checkpoint = tmp_path / "flux-2-klein-9b-fp8.safetensors"
    checkpoint.touch()
    calls: dict[str, tuple] = {}
    transformer = object()
    pipeline = object()

    class FakeTransformer:
        @classmethod
        def from_single_file(cls, path, **kwargs):
            calls["transformer"] = (path, kwargs)
            return transformer

    class FakePipeline:
        @classmethod
        def from_pretrained(cls, path, **kwargs):
            calls["pipeline"] = (path, kwargs)
            return pipeline

    classes = {
        "Flux2Transformer2DModel": FakeTransformer,
        "Flux2KleinPipeline": FakePipeline,
    }
    monkeypatch.setattr(image_generate, "local_repo_path", lambda _mode: tmp_path)
    monkeypatch.setattr(image_generate, "_import_diffusers_class", lambda name: classes[name])

    runner = object.__new__(image_generate._FluxKleinFp8Runner)
    runner.mode = GenerateMode.FLUX2_KLEIN_9B_FP8
    runner.dtype = torch.bfloat16

    assert runner._load_pipeline() is pipeline
    transformer_path, transformer_kwargs = calls["transformer"]
    assert transformer_path == str(checkpoint)
    assert transformer_kwargs["config"] == str(tmp_path)
    assert transformer_kwargs["subfolder"] == "transformer"
    assert transformer_kwargs["local_files_only"] is True
    pipeline_path, pipeline_kwargs = calls["pipeline"]
    assert pipeline_path == str(tmp_path)
    assert pipeline_kwargs["transformer"] is transformer
    assert pipeline_kwargs["local_files_only"] is True
