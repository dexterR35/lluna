"""Typed pixel-buffer metadata for editor and provider boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite


class BufferKind(str, Enum):
    RGB = "rgb"
    RGBA = "rgba"
    MASK = "mask"
    DEPTH = "depth"
    FLOW = "flow"
    NORMAL = "normal"


class ColorSpace(str, Enum):
    NONE = "none"
    SRGB = "srgb"
    DISPLAY_P3 = "display-p3"
    REC709 = "rec709"
    REC2020 = "rec2020"
    ACESCG = "acescg"


class TransferFunction(str, Enum):
    NONE = "none"
    LINEAR = "linear"
    SRGB = "srgb"
    GAMMA24 = "gamma24"
    PQ = "pq"
    HLG = "hlg"


class AlphaMode(str, Enum):
    NONE = "none"
    STRAIGHT = "straight"
    PREMULTIPLIED = "premultiplied"


_CHANNELS = {
    BufferKind.RGB: 3,
    BufferKind.RGBA: 4,
    BufferKind.MASK: 1,
    BufferKind.DEPTH: 1,
    BufferKind.FLOW: 2,
    BufferKind.NORMAL: 3,
}
_DTYPES = {"uint8", "uint16", "float16", "float32"}


@dataclass(frozen=True)
class PixelTransform:
    """Affine project-space transform stored as a row-major 3×3 matrix."""

    values: tuple[float, ...] = (
        1.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.0,
        0.0,
        1.0,
    )

    def __post_init__(self) -> None:
        if len(self.values) != 9:
            raise ValueError("pixel transform must contain exactly 9 values")
        if not all(isfinite(float(value)) for value in self.values):
            raise ValueError("pixel transform values must be finite")
        determinant = (
            self.values[0]
            * (self.values[4] * self.values[8] - self.values[5] * self.values[7])
            - self.values[1]
            * (self.values[3] * self.values[8] - self.values[5] * self.values[6])
            + self.values[2]
            * (self.values[3] * self.values[7] - self.values[4] * self.values[6])
        )
        if abs(determinant) < 1e-12:
            raise ValueError("pixel transform must be invertible")


@dataclass(frozen=True)
class MediaBufferDescriptor:
    """Serializable facts required to interpret a pixel buffer correctly."""

    kind: BufferKind
    width: int
    height: int
    channels: int
    dtype: str
    color_space: ColorSpace
    transfer: TransferFunction
    alpha_mode: AlphaMode = AlphaMode.NONE
    transform_to_source: PixelTransform = PixelTransform()

    def __post_init__(self) -> None:
        if self.width < 1 or self.height < 1:
            raise ValueError("buffer dimensions must be positive")
        expected = _CHANNELS[self.kind]
        if self.channels != expected:
            raise ValueError(
                f"{self.kind.value} buffers require {expected} channel(s), "
                f"got {self.channels}"
            )
        if self.dtype not in _DTYPES:
            raise ValueError(f"unsupported buffer dtype: {self.dtype}")
        colorless = self.kind in {BufferKind.MASK, BufferKind.DEPTH, BufferKind.FLOW}
        if colorless and (
            self.color_space is not ColorSpace.NONE
            or self.transfer is not TransferFunction.NONE
        ):
            raise ValueError(f"{self.kind.value} buffers cannot declare a color space")
        if not colorless and (
            self.color_space is ColorSpace.NONE
            or self.transfer is TransferFunction.NONE
        ):
            raise ValueError(f"{self.kind.value} buffers require color metadata")
        if self.kind is BufferKind.RGBA:
            if self.alpha_mode is AlphaMode.NONE:
                raise ValueError("RGBA buffers must declare an alpha mode")
        elif self.alpha_mode is not AlphaMode.NONE:
            raise ValueError(f"{self.kind.value} buffers cannot declare alpha")

    @classmethod
    def srgb_rgba(
        cls,
        width: int,
        height: int,
        *,
        dtype: str = "uint8",
        alpha_mode: AlphaMode = AlphaMode.STRAIGHT,
    ) -> MediaBufferDescriptor:
        return cls(
            kind=BufferKind.RGBA,
            width=width,
            height=height,
            channels=4,
            dtype=dtype,
            color_space=ColorSpace.SRGB,
            transfer=TransferFunction.SRGB,
            alpha_mode=alpha_mode,
        )

    @classmethod
    def mask(
        cls,
        width: int,
        height: int,
        *,
        dtype: str = "uint8",
        transform_to_source: PixelTransform = PixelTransform(),
    ) -> MediaBufferDescriptor:
        return cls(
            kind=BufferKind.MASK,
            width=width,
            height=height,
            channels=1,
            dtype=dtype,
            color_space=ColorSpace.NONE,
            transfer=TransferFunction.NONE,
            transform_to_source=transform_to_source,
        )
