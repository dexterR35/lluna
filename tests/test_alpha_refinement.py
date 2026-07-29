from __future__ import annotations

import numpy as np
import pytest

from backend.editor.alpha_refinement import (
    AlphaRefinementOptions,
    merge_protect_alpha,
    refine_alpha_cutout,
)


def _source(size: int = 17) -> np.ndarray:
    rgb = np.zeros((size, size, 3), dtype=np.uint8)
    rgb[:, :] = (15, 180, 30)
    rgb[4:-4, 4:-4] = (190, 35, 20)
    return rgb


def test_disabled_refinement_without_protect_is_exact_identity() -> None:
    rgb = _source()
    alpha = np.arange(rgb.shape[0] * rgb.shape[1], dtype=np.uint8).reshape(
        rgb.shape[:2]
    )
    rgb_before = rgb.copy()
    alpha_before = alpha.copy()

    result = refine_alpha_cutout(rgb, alpha, AlphaRefinementOptions())

    assert np.array_equal(result.rgba[:, :, :3], rgb_before)
    assert np.array_equal(result.rgba[:, :, 3], alpha_before)
    assert result.protected_pixels == 0
    assert result.changed_alpha_pixels == 0
    assert np.array_equal(rgb, rgb_before)
    assert np.array_equal(alpha, alpha_before)


def test_binary_protect_forces_any_marked_pixel_opaque() -> None:
    alpha = np.full((4, 5), 30, dtype=np.uint8)
    protect = np.zeros_like(alpha)
    protect[1, 2] = 1
    protect[2, 3] = 128

    merged, count = merge_protect_alpha(alpha, protect, mode="binary")

    assert count == 2
    assert merged[1, 2] == 255
    assert merged[2, 3] == 255
    assert merged[0, 0] == 30


def test_soft_protect_uses_maximum_instead_of_addition() -> None:
    alpha = np.array([[10, 100, 240]], dtype=np.uint8)
    protect = np.array([[50, 80, 250]], dtype=np.uint8)

    merged, count = merge_protect_alpha(alpha, protect, mode="soft")

    assert count == 3
    assert merged.tolist() == [[50, 100, 250]]


def test_empty_protect_is_an_exact_no_op() -> None:
    alpha = np.arange(20, dtype=np.uint8).reshape(4, 5)
    merged, count = merge_protect_alpha(alpha, np.zeros_like(alpha))

    assert count == 0
    assert np.array_equal(merged, alpha)
    assert merged is not alpha


def test_expand_and_contract_move_alpha_boundary() -> None:
    rgb = _source()
    alpha = np.zeros(rgb.shape[:2], dtype=np.uint8)
    alpha[7:10, 7:10] = 255

    expanded = refine_alpha_cutout(
        rgb,
        alpha,
        AlphaRefinementOptions(enabled=True, contract_expand_px=2),
    )
    contracted = refine_alpha_cutout(
        rgb,
        alpha,
        AlphaRefinementOptions(enabled=True, contract_expand_px=-1),
    )

    assert np.count_nonzero(expanded.rgba[:, :, 3]) > np.count_nonzero(alpha)
    assert np.count_nonzero(contracted.rgba[:, :, 3]) < np.count_nonzero(alpha)


def test_component_cleanup_removes_island_and_fills_small_hole() -> None:
    rgb = _source(21)
    alpha = np.zeros(rgb.shape[:2], dtype=np.uint8)
    alpha[4:17, 4:17] = 255
    alpha[10, 10] = 0
    alpha[1, 1] = 255

    result = refine_alpha_cutout(
        rgb,
        alpha,
        AlphaRefinementOptions(
            enabled=True,
            remove_islands_below_px=2,
            fill_holes_below_px=2,
        ),
    )
    refined = result.rgba[:, :, 3]

    assert refined[1, 1] == 0
    assert refined[10, 10] == 255


def test_edge_smoothing_and_feather_produce_soft_transition() -> None:
    rgb = _source()
    alpha = np.zeros(rgb.shape[:2], dtype=np.uint8)
    alpha[5:12, 5:12] = 255

    result = refine_alpha_cutout(
        rgb,
        alpha,
        AlphaRefinementOptions(
            enabled=True,
            edge_smoothing_radius_px=2,
            feather_radius_px=2,
        ),
    )
    refined = result.rgba[:, :, 3]

    assert np.any((refined > 0) & (refined < 255))


def test_decontamination_does_not_change_refined_alpha() -> None:
    rgb = _source()
    alpha = np.zeros(rgb.shape[:2], dtype=np.uint8)
    alpha[4:13, 4:13] = 120
    alpha[6:11, 6:11] = 255
    rgb[4:13, 4:13] = (15, 180, 30)
    rgb[6:11, 6:11] = (190, 35, 20)

    without = refine_alpha_cutout(
        rgb,
        alpha,
        AlphaRefinementOptions(enabled=True),
    )
    with_cleanup = refine_alpha_cutout(
        rgb,
        alpha,
        AlphaRefinementOptions(enabled=True, decontaminate_rgb=True),
    )

    assert np.array_equal(without.rgba[:, :, 3], with_cleanup.rgba[:, :, 3])
    assert np.any(without.rgba[:, :, :3] != with_cleanup.rgba[:, :, :3])


def test_invalid_or_unknown_options_are_rejected() -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        AlphaRefinementOptions(decontaminate_strength=1.1)
    with pytest.raises(ValueError, match="unknown alpha-refinement"):
        AlphaRefinementOptions.from_mapping({"mystery": True})
