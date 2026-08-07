from __future__ import annotations

import torch
from PIL import Image
from types import SimpleNamespace

from backend.ai.runtimes.diffusion import _DiffusersRunner
from backend.tools.inference.worker import _encode_preview_frame


def test_encode_preview_frame_downscales_and_encodes_as_jpeg_data_url():
    image = Image.new("RGB", (800, 600), color=(100, 150, 200))
    data_url = _encode_preview_frame(image, max_edge=200)
    assert data_url.startswith("data:image/jpeg;base64,")
    assert len(data_url) < 20000  # a downscaled JPEG thumbnail, not the original


def test_encode_preview_frame_leaves_small_images_unscaled():
    image = Image.new("RGB", (64, 64), color=(0, 0, 0))
    data_url = _encode_preview_frame(image, max_edge=384)
    assert data_url.startswith("data:image/jpeg;base64,")


class _FakeVAEConfig:
    scaling_factor = 0.18215
    shift_factor = 0.0


class _FakeVAE:
    config = _FakeVAEConfig()

    def decode(self, sample, return_dict=False):
        b, c, h, w = sample.shape
        return (torch.zeros(b, 3, h, w),)


class _FakeProcessor:
    def postprocess(self, decoded, output_type="pil"):
        return [Image.new("RGB", (decoded.shape[-1], decoded.shape[-2]))]


def _runner_with_pipe(**pipe_kwargs) -> _DiffusersRunner:
    runner = object.__new__(_DiffusersRunner)
    runner.pipe = SimpleNamespace(**pipe_kwargs)
    return runner


def test_decode_latents_preview_handles_spatial_4d_latents():
    runner = _runner_with_pipe(vae=_FakeVAE(), image_processor=_FakeProcessor())
    frame = runner._decode_latents_preview(torch.randn(1, 4, 16, 16), width=128, height=128)
    assert isinstance(frame, Image.Image)


def test_decode_latents_preview_unpacks_flux_style_packed_latents():
    def unpack(latents, height, width, scale_factor):
        b, seq, c = latents.shape
        side = int(seq**0.5)
        return latents.transpose(1, 2).reshape(b, c, side, side)

    runner = _runner_with_pipe(
        vae=_FakeVAE(),
        image_processor=_FakeProcessor(),
        _unpack_latents=unpack,
        vae_scale_factor=8,
    )
    frame = runner._decode_latents_preview(torch.randn(1, 16, 4), width=128, height=128)
    assert isinstance(frame, Image.Image)


def test_decode_latents_preview_returns_none_without_unpack_support():
    runner = _runner_with_pipe(vae=_FakeVAE())  # no `_unpack_latents` attribute
    frame = runner._decode_latents_preview(torch.randn(1, 16, 4), width=128, height=128)
    assert frame is None


def test_decode_latents_preview_returns_none_without_vae():
    runner = _runner_with_pipe()
    frame = runner._decode_latents_preview(torch.randn(1, 4, 8, 8), width=64, height=64)
    assert frame is None


def test_callback_never_raises_when_preview_decode_fails():
    class _BrokenVAE:
        config = _FakeVAEConfig()

        def decode(self, *a, **k):
            raise RuntimeError("simulated decode failure")

    runner = _runner_with_pipe(vae=_BrokenVAE())
    received = []
    # Must not raise even though the decode inside it fails.
    runner._callback(
        step=0,
        steps=4,
        progress=None,
        cancel_event=None,
        generation=0,
        latents=torch.randn(1, 4, 8, 8),
        preview=received.append,
        preview_interval=1,
        width=64,
        height=64,
    )
    assert received == []


def test_callback_delivers_preview_on_interval_steps_only():
    runner = _runner_with_pipe(vae=_FakeVAE(), image_processor=_FakeProcessor())
    received = []
    for step in range(6):
        runner._callback(
            step=step,
            steps=6,
            progress=None,
            cancel_event=None,
            generation=0,
            latents=torch.randn(1, 4, 8, 8),
            preview=received.append,
            preview_interval=2,
            width=64,
            height=64,
        )
    # steps 0, 2, 4 (interval) plus 5 (final step) = 4 frames out of 6 steps.
    assert len(received) == 4
