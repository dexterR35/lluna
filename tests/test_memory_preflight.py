from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.tools.shared import memory


def _with_free_mb(free_mb: float, total_mb: float = 24000.0):
    return patch.object(memory, "_free_total_mb", return_value=(free_mb, total_mb))


def test_preflight_minimum_treats_undeclared_as_noop():
    # <= 0 means "this model doesn't declare a minimum" - never block on it.
    with _with_free_mb(100.0):
        budget = memory.preflight_minimum("Some Model", 0)
    assert budget.estimated_mb == 0.0


def test_preflight_minimum_raises_with_tag_and_hint():
    with _with_free_mb(5000.0):
        with pytest.raises(memory.VramBudgetError, match=r"for My Model.*Free some memory\.$"):
            memory.preflight_minimum("My Model", 8000, hint="Free some memory.")


def test_preflight_minimum_passes_when_enough_free():
    with _with_free_mb(9000.0):
        budget = memory.preflight_minimum("My Model", 8000)
    assert budget.estimated_mb == 8000


def test_preflight_minimum_allows_declared_cpu_offload_when_vram_is_low():
    with _with_free_mb(6000.0):
        budget = memory.preflight_minimum(
            "Qwen-Image",
            12000,
            allow_cpu_offload=True,
        )

    assert budget.estimated_mb == 12000
    assert budget.free_mb == 6000


def test_preflight_birefnet_is_a_noop_without_cuda():
    with patch.object(memory, "_free_total_mb", return_value=(0.0, 0.0)):
        budget = memory.preflight_birefnet(2304, precision="fp32")
    assert budget.estimated_mb == 0.0


def test_preflight_birefnet_scales_with_resolution_not_native_image_size():
    # Same free VRAM, only the inference `resolution` param differs - a
    # low-res request should fit where a high-res one doesn't.
    with _with_free_mb(1500.0):
        low = memory.preflight_birefnet(512, precision="fp32")
        with pytest.raises(memory.VramBudgetError, match="Lower Inference resolution"):
            memory.preflight_birefnet(2304, precision="fp32")
    assert low.estimated_mb > 0


def test_preflight_birefnet_fp16_needs_less_than_fp32():
    with _with_free_mb(100000.0):
        fp16 = memory.preflight_birefnet(2048, precision="auto")
        fp32 = memory.preflight_birefnet(2048, precision="fp32")
    assert fp16.estimated_mb < fp32.estimated_mb


def test_preflight_supir_is_a_noop_without_cuda():
    with patch.object(memory, "_free_total_mb", return_value=(0.0, 0.0)):
        budget = memory.preflight_supir(use_llava=True)
    assert budget.estimated_mb == 0.0


def test_preflight_supir_base_requirement():
    with _with_free_mb(6000.0):
        with pytest.raises(memory.VramBudgetError, match="Free up GPU memory\\.$"):
            memory.preflight_supir(use_llava=False)
    with _with_free_mb(15000.0):
        budget = memory.preflight_supir(use_llava=False)
    assert budget.estimated_mb == memory._SUPIR_MINIMUM_VRAM_MB


def test_preflight_supir_accounts_for_llava_precision():
    # 15GB free: enough for SUPIR alone, not enough with fp16 LLaVA, enough
    # with 8-bit LLaVA only if it stays under the smaller extra allowance.
    with _with_free_mb(15000.0):
        with pytest.raises(memory.VramBudgetError, match="8-bit LLaVA"):
            memory.preflight_supir(use_llava=True, load_8bit_llava=False)
    with _with_free_mb(17000.0):
        budget = memory.preflight_supir(use_llava=True, load_8bit_llava=True)
    assert budget.estimated_mb == (
        memory._SUPIR_MINIMUM_VRAM_MB + memory._SUPIR_LLAVA_8BIT_EXTRA_MB
    )


def test_preflight_supir_8bit_still_short_suggests_disabling_llava():
    with _with_free_mb(15000.0):
        with pytest.raises(memory.VramBudgetError, match="Turn off automatic LLaVA"):
            memory.preflight_supir(use_llava=True, load_8bit_llava=True)


def test_preflight_seedvr_unknown_model_is_a_noop():
    with _with_free_mb(1000.0):
        budget = memory.preflight_seedvr("some-future-model")
    assert budget.estimated_mb == 0.0


def test_preflight_seedvr_3b_vs_7b_thresholds():
    with _with_free_mb(30000.0):
        small = memory.preflight_seedvr("seedvr2-3b")
        with pytest.raises(memory.VramBudgetError, match="Try the 3B model instead"):
            memory.preflight_seedvr("seedvr2-7b")
    assert small.estimated_mb == 24576.0


def test_preflight_seedvr_3b_short_does_not_suggest_itself():
    with _with_free_mb(10000.0):
        with pytest.raises(memory.VramBudgetError) as excinfo:
            memory.preflight_seedvr("seedvr2-3b")
    assert "3B model instead" not in str(excinfo.value)
