from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from backend.editor.inspection import (
    InspectionMode,
    align_for_comparison,
    checkerboard,
    composite_on,
    render_inspection,
    wipe_comparison,
)


def _pair() -> tuple[Image.Image, Image.Image]:
    original = Image.new("RGBA", (6, 4), (20, 40, 60, 255))
    result_array = np.zeros((4, 6, 4), dtype=np.uint8)
    result_array[:, :, :3] = (20, 40, 60)
    result_array[:, :3, 3] = 255
    return original, Image.fromarray(result_array, mode="RGBA")


def test_checkerboard_is_opaque_and_alternates_tiles() -> None:
    board = np.asarray(checkerboard((4, 4), tile=2))

    assert np.all(board[:, :, 3] == 255)
    assert np.array_equal(board[0, 0, :3], board[1, 1, :3])
    assert not np.array_equal(board[0, 0, :3], board[0, 2, :3])


def test_alpha_inspection_is_exact_grayscale() -> None:
    original, result = _pair()
    alpha = np.asarray(render_inspection(original, result, InspectionMode.ALPHA))

    assert np.all(alpha[:, :3, :3] == 255)
    assert np.all(alpha[:, 3:, :3] == 0)
    assert np.all(alpha[:, :, 3] == 255)


def test_black_and_white_views_composite_transparency() -> None:
    original, result = _pair()
    black = np.asarray(render_inspection(original, result, InspectionMode.BLACK))
    white = np.asarray(render_inspection(original, result, InspectionMode.WHITE))

    assert np.all(black[:, 3:, :3] == 0)
    assert np.all(white[:, 3:, :3] == 255)
    assert np.all(black[:, :3, :3] == (20, 40, 60))


def test_red_overlay_marks_removed_pixels_only() -> None:
    original, result = _pair()
    overlay = np.asarray(render_inspection(original, result, InspectionMode.RED_OVERLAY))

    assert np.all(overlay[:, :3, :3] == (20, 40, 60))
    assert np.all(overlay[:, 3:, 0] > overlay[:, 3:, 1])


def test_difference_exposes_removed_region() -> None:
    original, result = _pair()
    difference = np.asarray(render_inspection(original, result, InspectionMode.DIFFERENCE))

    assert np.all(difference[:, 3:, 0] == 255)
    assert np.any(difference[:, 3:, :3] != 0)


def test_wipe_uses_original_left_and_result_visual_right() -> None:
    original, result = _pair()
    wipe = np.asarray(wipe_comparison(original, result, 0.5))

    assert np.all(wipe[:, :2, :3] == (20, 40, 60))
    assert np.all(wipe[:, 2:4, :3] == 255)  # two-pixel divider
    assert np.any(wipe[:, 4:, :3] != (20, 40, 60))


def test_alignment_resamples_original_to_result_size() -> None:
    original = Image.new("RGB", (2, 2), "red")
    result = Image.new("RGBA", (4, 6), "blue")

    before, after, resampled = align_for_comparison(original, result)

    assert before.size == after.size == (4, 6)
    assert resampled


def test_composite_requires_matching_image_background() -> None:
    _, result = _pair()
    with pytest.raises(ValueError, match="dimensions"):
        composite_on(result, Image.new("RGBA", (2, 2)))


def test_wipe_position_is_validated() -> None:
    original, result = _pair()
    with pytest.raises(ValueError, match="between 0 and 1"):
        wipe_comparison(original, result, 1.1)
