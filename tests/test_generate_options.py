from __future__ import annotations

import pytest

from backend.tools.constant import GenerateMode
from backend.tools.generate_models import (
    MODEL_CATALOG,
    _validate_download_snapshot,
    catalog_info,
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
        (GenerateMode.FLUX2_KLEIN_BASE_4B, list(range(1, 101)), 50, 4.0),
        (GenerateMode.FLUX2_KLEIN_BASE_9B, list(range(1, 101)), 50, 4.0),
        (GenerateMode.SDXL_TURBO, [1, 2, 4], 1, 0.0),
        (GenerateMode.SD15, [20, 50, 75], 50, 7.5),
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
    assert validate_steps_for_mode(GenerateMode.FLUX2_KLEIN_BASE_4B, 50) == 50
    assert validate_steps_for_mode(GenerateMode.FLUX2_KLEIN_BASE_4B, 100) == 100


def test_model_specific_size_defaults() -> None:
    assert default_size_preset_for_mode(GenerateMode.FLUX2_KLEIN_4B).width == 1024
    assert default_size_preset_for_mode(GenerateMode.SDXL_TURBO).width == 512
    assert [
        (preset.width, preset.height)
        for preset in size_presets_for_mode(GenerateMode.SD15)
    ] == [(512, 512)]


def test_generate_downloads_keep_only_one_runtime_weight_layout() -> None:
    for info in MODEL_CATALOG:
        patterns = "\n".join(info.download_allow_patterns)
        assert ".bin" not in patterns
        assert ".ckpt" not in patterns
        assert "safety_checker" not in patterns
        assert "onnx" not in patterns
        assert "non_ema" not in patterns
        assert "model_index.json" in info.download_allow_patterns

    flux = catalog_info(GenerateMode.FLUX2_KLEIN_BASE_4B)
    assert flux is not None
    assert "transformer/*.safetensors" in flux.download_allow_patterns
    assert "*.safetensors" not in flux.download_allow_patterns

    for mode in (GenerateMode.SDXL_TURBO, GenerateMode.SD15):
        info = catalog_info(mode)
        assert info is not None
        assert info.weight_variant == "fp16"
        assert "unet/*.fp16.safetensors" in info.download_allow_patterns


@pytest.mark.parametrize(
    "mode",
    [
        GenerateMode.FLUX2_KLEIN_BASE_4B,
        GenerateMode.SDXL_TURBO,
        GenerateMode.SD15,
    ],
)
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
    if info.pipeline == "flux":
        required.extend(
            [
                "transformer/config.json",
                "transformer/diffusion_pytorch_model.safetensors",
            ]
        )
    else:
        required.extend(
            [
                "unet/config.json",
                "unet/diffusion_pytorch_model.fp16.safetensors",
            ]
        )
    if info.pipeline == "sdxl_turbo":
        required.extend(
            [
                "text_encoder_2/config.json",
                "text_encoder_2/model.fp16.safetensors",
                "tokenizer_2/tokenizer_config.json",
            ]
        )

    for relative in required:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    _validate_download_snapshot(info, tmp_path)
    (tmp_path / "vae/diffusion_pytorch_model.fp16.safetensors").unlink()
    with pytest.raises(RuntimeError, match=r"vae/\*\.safetensors"):
        _validate_download_snapshot(info, tmp_path)
