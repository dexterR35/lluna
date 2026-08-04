from __future__ import annotations

import numpy as np

from backend.media.mask_layers import MaskLayerStack, mask_roi


def test_fill_and_protect_layers_compose_without_destroying_sources() -> None:
    stack = MaskLayerStack(12, 10)
    stack.active.mask[2:8, 2:10] = 255
    stack.add_layer(protect=True)
    stack.active.mask[4:6, 5:7] = 255

    composite = stack.composite()

    assert np.all(composite[2:4, 2:10] == 255)
    assert np.all(composite[4:6, 5:7] == 0)
    assert np.all(stack.fill_mask()[4:6, 5:7] == 255)
    assert np.all(stack.protect_mask()[4:6, 5:7] == 255)


def test_independent_layers_can_be_switched_and_removed() -> None:
    stack = MaskLayerStack(8, 8)
    stack.active.mask[1, 1] = 255
    stack.add_layer(name="Second")
    stack.active.mask[6, 6] = 255

    stack.set_active(0)
    assert stack.active.mask[1, 1] == 255
    stack.remove_active()

    assert len(stack.layers) == 1
    assert stack.active.name == "Second"
    assert stack.active.mask[6, 6] == 255


def test_mask_refinement_grow_shrink_feather_and_edge() -> None:
    stack = MaskLayerStack(32, 32)
    stack.active.mask[12:20, 12:20] = 255
    original_pixels = np.count_nonzero(stack.active.mask)

    stack.transform_active("grow", radius=2)
    assert np.count_nonzero(stack.active.mask) > original_pixels

    stack.transform_active("shrink", radius=1)
    stack.transform_active("feather", radius=3)
    assert np.any((stack.active.mask > 0) & (stack.active.mask < 255))

    guide = np.zeros((32, 32, 4), dtype=np.uint8)
    guide[:, :16, :3] = 20
    guide[:, 16:, :3] = 240
    guide[:, :, 3] = 255
    stack.transform_active("edge", radius=3, guide_rgba=guide)
    assert stack.active.mask.dtype == np.uint8


def test_layer_project_round_trip(tmp_path) -> None:
    stack = MaskLayerStack(9, 7)
    stack.active.mask[1:4, 2:5] = 180
    stack.add_layer(name="Hands", protect=True)
    stack.active.mask[3:6, 4:8] = 255
    path = tmp_path / "mask-project.npz"

    stack.save(path)
    loaded = MaskLayerStack.load(path)

    assert loaded.active_index == 1
    assert [layer.name for layer in loaded.layers] == ["Fill 1", "Hands"]
    assert [layer.protect for layer in loaded.layers] == [False, True]
    assert np.array_equal(loaded.layers[0].mask, stack.layers[0].mask)
    assert np.array_equal(loaded.layers[1].mask, stack.layers[1].mask)


def test_mask_roi_is_padded_aligned_and_clamped() -> None:
    mask = np.zeros((100, 120), dtype=np.uint8)
    mask[40:50, 60:70] = 255

    assert mask_roi(mask, padding=10, align=8) == (48, 24, 80, 64)
    assert mask_roi(np.zeros_like(mask)) is None

    mask[0, 0] = 255
    left, top, right, bottom = mask_roi(mask, padding=20, align=8)
    assert left == 0
    assert top == 0
    assert right <= 120
    assert bottom <= 100
