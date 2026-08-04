"""Shared frame-to-tensor transforms used by runtime inpainting models."""

from __future__ import annotations

from collections.abc import Sequence

import cv2
import numpy as np
import torch
from PIL import Image
from torchvision import transforms


class Stack:
    def __init__(self, roll: bool = False) -> None:
        self.roll = roll

    def __call__(self, images: Sequence[Image.Image | np.ndarray]) -> np.ndarray:
        normalized: list[Image.Image] = []
        for image in images:
            if isinstance(image, np.ndarray):
                if image.ndim == 3:
                    image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
                elif image.ndim == 2:
                    image = Image.fromarray(image)
                else:
                    raise ValueError(f"Unsupported image array shape: {image.shape}")
            normalized.append(image)

        if not normalized:
            raise ValueError("At least one image is required")
        mode = normalized[0].mode
        if mode == "1":
            normalized = [image.convert("L") for image in normalized]
            mode = "L"
        if mode == "L":
            return np.stack([np.expand_dims(image, 2) for image in normalized], axis=2)
        if mode == "RGB":
            if self.roll:
                return np.stack([np.asarray(image)[:, :, ::-1] for image in normalized], axis=2)
            return np.stack(normalized, axis=2)
        raise NotImplementedError(f"Image mode {mode}")


class ToTorchFormatTensor:
    def __init__(self, div: bool = True) -> None:
        self.div = div

    def __call__(self, value: Image.Image | np.ndarray) -> torch.Tensor:
        if isinstance(value, np.ndarray):
            tensor = torch.from_numpy(value).permute(2, 3, 0, 1).contiguous()
        else:
            array = np.asarray(value)
            if array.ndim == 2:
                array = array[:, :, None]
            tensor = torch.from_numpy(array.copy()).permute(2, 0, 1).contiguous()
        return tensor.float().div(255) if self.div else tensor.float()


def to_tensors():
    return transforms.Compose([Stack(), ToTorchFormatTensor()])
