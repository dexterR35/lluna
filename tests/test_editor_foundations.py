from __future__ import annotations

import pytest

from backend.editor.buffers import (
    AlphaMode,
    BufferKind,
    ColorSpace,
    MediaBufferDescriptor,
    PixelTransform,
    TransferFunction,
)
from backend.editor.operations import Locality, OperationContract


def test_srgb_rgba_descriptor_is_explicit_and_valid() -> None:
    descriptor = MediaBufferDescriptor.srgb_rgba(1920, 1080)

    assert descriptor.kind is BufferKind.RGBA
    assert descriptor.channels == 4
    assert descriptor.color_space is ColorSpace.SRGB
    assert descriptor.transfer is TransferFunction.SRGB
    assert descriptor.alpha_mode is AlphaMode.STRAIGHT


def test_mask_descriptor_rejects_color_metadata() -> None:
    with pytest.raises(ValueError, match="cannot declare a color space"):
        MediaBufferDescriptor(
            kind=BufferKind.MASK,
            width=32,
            height=32,
            channels=1,
            dtype="uint8",
            color_space=ColorSpace.SRGB,
            transfer=TransferFunction.SRGB,
        )


def test_rgba_descriptor_requires_declared_alpha_mode() -> None:
    with pytest.raises(ValueError, match="declare an alpha mode"):
        MediaBufferDescriptor(
            kind=BufferKind.RGBA,
            width=32,
            height=32,
            channels=4,
            dtype="uint8",
            color_space=ColorSpace.SRGB,
            transfer=TransferFunction.SRGB,
        )


def test_pixel_transform_rejects_non_invertible_matrix() -> None:
    with pytest.raises(ValueError, match="invertible"):
        PixelTransform((1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0))


def test_operation_contract_requires_namespace_and_valid_padding() -> None:
    with pytest.raises(ValueError, match="namespaced"):
        OperationContract(
            operation_type="refine",
            schema_version=1,
            input_kinds=(BufferKind.MASK,),
            output_kinds=(BufferKind.MASK,),
            locality=Locality.LOCAL,
        )
    with pytest.raises(ValueError, match="cannot be negative"):
        OperationContract(
            operation_type="alpha.refine",
            schema_version=1,
            input_kinds=(BufferKind.MASK,),
            output_kinds=(BufferKind.MASK,),
            locality=Locality.LOCAL,
            padding_px=-1,
        )
