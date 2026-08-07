from __future__ import annotations

import pytest

from backend.ai.runtimes.diffusion import _resolve_dtype
from backend.tools.shared.constants import GenerateMode


def test_int4_is_rejected_for_built_in_models() -> None:
    with pytest.raises(ValueError, match="custom models"):
        _resolve_dtype(GenerateMode.FLUX2_DEV, "int4")


def test_int8_is_rejected_for_built_in_models() -> None:
    with pytest.raises(ValueError, match="custom models"):
        _resolve_dtype(GenerateMode.FLUX2_DEV, "int8")


def test_fp32_is_rejected_when_the_model_only_declares_bf16_fp16() -> None:
    # FLUX2_DEV's reviewed contract (backend/models/reference/capabilities.py)
    # declares dtypes=("bf16", "fp16") only - fp32 was previously accepted for
    # every built-in model regardless of what its contract declared.
    with pytest.raises(ValueError, match="only declares support for"):
        _resolve_dtype(GenerateMode.FLUX2_DEV, "fp32")


def test_declared_dtype_still_resolves_for_built_in_models() -> None:
    import torch

    assert _resolve_dtype(GenerateMode.FLUX2_DEV, "fp16") == torch.float16


def test_fp8_only_model_rejects_bf16_and_resolves_fp8() -> None:
    import torch

    with pytest.raises(ValueError, match="only declares support for"):
        _resolve_dtype(GenerateMode.FLUX2_KLEIN_9B_FP8, "bf16")
    float8 = getattr(torch, "float8_e4m3fn", None)
    if float8 is not None:
        assert _resolve_dtype(GenerateMode.FLUX2_KLEIN_9B_FP8, "fp8") == float8
