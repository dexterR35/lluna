from __future__ import annotations

import pytest

from backend.ai.runtimes.diffusion import _resolve_dtype


def test_int4_is_rejected_for_built_in_models() -> None:
    with pytest.raises(ValueError, match="custom models"):
        _resolve_dtype("int4")


def test_int8_is_rejected_for_built_in_models() -> None:
    with pytest.raises(ValueError, match="custom models"):
        _resolve_dtype("int8")


def test_fp32_still_resolves_for_built_in_models() -> None:
    import torch

    assert _resolve_dtype("fp32") == torch.float32
