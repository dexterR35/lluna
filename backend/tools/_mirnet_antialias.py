"""Binomial low-pass stride-2 downsample used by MIRNet ResidualDownSample.

Same filter family as antialiased-cnns (fixed binomial kernel, no learnable
params). Written for Lluna so MIRNet LOL checkpoints stay compatible.
"""

from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


class Downsample(nn.Module):
    def __init__(
        self,
        pad_type: str = "reflect",
        filt_size: int = 3,
        stride: int = 2,
        channels: int | None = None,
        pad_off: int = 0,
    ):
        super().__init__()
        if channels is None:
            raise ValueError("Downsample requires channels=")
        self.filt_size = int(filt_size)
        self.pad_off = int(pad_off)
        self.stride = int(stride)
        self.channels = int(channels)

        pad = int(1.0 * (self.filt_size - 1) / 2)
        pad_ceil = int(np.ceil(1.0 * (self.filt_size - 1) / 2))
        self.pad_sizes = [
            pad + self.pad_off,
            pad_ceil + self.pad_off,
            pad + self.pad_off,
            pad_ceil + self.pad_off,
        ]

        coeffs = {
            1: [1.0],
            2: [1.0, 1.0],
            3: [1.0, 2.0, 1.0],
            4: [1.0, 3.0, 3.0, 1.0],
            5: [1.0, 4.0, 6.0, 4.0, 1.0],
        }
        if self.filt_size not in coeffs:
            raise ValueError(f"Unsupported filt_size={self.filt_size}")
        a = np.asarray(coeffs[self.filt_size], dtype=np.float64)
        filt = torch.tensor(a[:, None] * a[None, :], dtype=torch.float32)
        filt = filt / filt.sum()
        self.register_buffer(
            "filt",
            filt[None, None, :, :].repeat(self.channels, 1, 1, 1),
        )

        if pad_type in ("refl", "reflect"):
            self.pad = nn.ReflectionPad2d(self.pad_sizes)
        elif pad_type in ("repl", "replicate"):
            self.pad = nn.ReplicationPad2d(self.pad_sizes)
        else:
            self.pad = nn.ZeroPad2d(self.pad_sizes)

    def forward(self, inp: torch.Tensor) -> torch.Tensor:
        if self.filt_size == 1:
            if self.pad_off == 0:
                return inp[:, :, :: self.stride, :: self.stride]
            return self.pad(inp)[:, :, :: self.stride, :: self.stride]
        return F.conv2d(self.pad(inp), self.filt, stride=self.stride, groups=inp.shape[1])
