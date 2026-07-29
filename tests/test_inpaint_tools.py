import numpy as np

from backend.tools.inpaint_tools import create_mask


def test_create_mask_accepts_float_coordinates_and_rounds_outward():
    mask = create_mask(
        (20, 30),
        [(5.8, 10.2, 6.7, 9.1)],
        expansion_px=2,
    )

    expected = np.zeros((20, 30), dtype=np.uint8)
    expected[4:13, 3:14] = 255
    np.testing.assert_array_equal(mask, expected)


def test_create_mask_clips_expanded_coordinates_to_image_bounds():
    mask = create_mask(
        (4, 5),
        [(-1.5, 5.5, -2.5, 4.5)],
        expansion_px=1,
    )

    np.testing.assert_array_equal(mask, np.full((4, 5), 255, dtype=np.uint8))
