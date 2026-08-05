"""Tests for safe denoise and cutout fringe cleanup."""

from __future__ import annotations

import threading

import numpy as np
import pytest

from backend.ai.runtimes.realesrgan import EnhanceCancelled, _preprocess_rgb
from backend.tools.media.cutout import decontaminate_rgb_fringe
from backend.tools.media.denoise import (
    denoise_rgb,
    estimate_noise_variance,
    verify_rgb,
)
from backend.tools.options.enhance import EnhanceOptions
from backend.tools.shared.constants import DenoiseStrength


def _soft_edge_rgba(size: int = 64) -> tuple[np.ndarray, np.ndarray]:
    """Opaque red core with blue-tinted fringe in soft alpha band."""
    alpha = np.zeros((size, size), dtype=np.uint8)
    rgb = np.zeros((size, size, 3), dtype=np.uint8)
    cx, cy = size // 2, size // 2
    for y in range(size):
        for x in range(size):
            d = max(abs(x - cx), abs(y - cy))
            if d <= size // 4:
                alpha[y, x] = 255
                rgb[y, x] = (220, 40, 40)
            elif d <= size // 4 + 3:
                alpha[y, x] = 120
                rgb[y, x] = (40, 40, 220)
    return rgb, alpha


class TestCutoutFringe:
    def test_alpha_not_mutated_by_caller(self):
        rgb, alpha = _soft_edge_rgba()
        alpha_before = alpha.copy()
        out = decontaminate_rgb_fringe(rgb, alpha)
        assert np.array_equal(alpha, alpha_before)
        assert out.shape == rgb.shape
        assert out.dtype == np.uint8

    def test_fringe_moves_toward_opaque_color(self):
        rgb, alpha = _soft_edge_rgba()
        out = decontaminate_rgb_fringe(rgb, alpha)
        fringe = (alpha >= 8) & (alpha <= 247)
        assert fringe.any()
        before_r = rgb[fringe, 0].mean()
        after_r = out[fringe, 0].mean()
        assert after_r > before_r


class TestSafeDenoise:
    def test_skip_if_clean_returns_identical(self):
        rgb = np.full((32, 32, 3), 128, dtype=np.uint8)
        gray = rgb[:, :, 0]
        assert estimate_noise_variance(gray) < 35.0
        out = denoise_rgb(rgb, DenoiseStrength.SAFE)
        assert np.array_equal(out, rgb)

    def test_noisy_input_changes_slightly(self):
        rng = np.random.default_rng(0)
        rgb = np.clip(rng.normal(128, 25, (48, 48, 3)), 0, 255).astype(np.uint8)
        assert estimate_noise_variance(rgb[:, :, 0]) >= 35.0
        out = denoise_rgb(rgb, DenoiseStrength.SAFE)
        assert out.shape == rgb.shape
        assert not np.array_equal(out, rgb)

    def test_verify_rejects_bad_output(self):
        ref = np.zeros((8, 8, 3), dtype=np.uint8)
        assert verify_rgb(ref, ref)
        assert not verify_rgb(ref.astype(np.float32), ref)
        assert not verify_rgb(ref[:, :4, :], ref)

    def test_cancel_raises(self):
        rgb = np.clip(np.random.default_rng(1).normal(100, 30, (40, 40, 3)), 0, 255).astype(
            np.uint8
        )
        ev = threading.Event()
        ev.set()
        with pytest.raises(EnhanceCancelled):
            denoise_rgb(rgb, cancel_event=ev, cancel_exc=EnhanceCancelled)


class TestPreprocess:
    def test_denoise_off_passthrough(self):
        rgb = np.full((16, 16, 3), 100, dtype=np.uint8)
        alpha = np.full((16, 16), 255, dtype=np.uint8)
        opts = EnhanceOptions(denoise=False)
        out = _preprocess_rgb(rgb, alpha, opts, None, 0, None)
        assert np.array_equal(out, rgb)
