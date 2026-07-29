"""Layered, full-resolution mask editing primitives."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass
class MaskLayer:
    name: str
    mask: np.ndarray
    visible: bool = True
    protect: bool = False

    def clone(self) -> "MaskLayer":
        return MaskLayer(self.name, self.mask.copy(), self.visible, self.protect)


class MaskLayerStack:
    """Ordered fill/protect layers sharing one canvas size."""

    def __init__(self, width: int, height: int) -> None:
        self.width = max(1, int(width))
        self.height = max(1, int(height))
        self.layers = [
            MaskLayer(
                "Fill 1",
                np.zeros((self.height, self.width), dtype=np.uint8),
            )
        ]
        self.active_index = 0

    @property
    def active(self) -> MaskLayer:
        return self.layers[self.active_index]

    def clone_layers(self) -> list[MaskLayer]:
        return [layer.clone() for layer in self.layers]

    def restore(self, layers: list[MaskLayer], active_index: int) -> None:
        valid = [layer.clone() for layer in layers if layer.mask.shape == (self.height, self.width)]
        if not valid:
            valid = [
                MaskLayer(
                    "Fill 1",
                    np.zeros((self.height, self.width), dtype=np.uint8),
                )
            ]
        self.layers = valid
        self.active_index = min(max(0, int(active_index)), len(valid) - 1)

    def add_layer(self, *, name: str | None = None, protect: bool = False) -> int:
        prefix = "Protect" if protect else "Fill"
        if not name:
            count = sum(layer.protect == protect for layer in self.layers) + 1
            name = f"{prefix} {count}"
        self.layers.append(
            MaskLayer(
                str(name),
                np.zeros((self.height, self.width), dtype=np.uint8),
                protect=bool(protect),
            )
        )
        self.active_index = len(self.layers) - 1
        return self.active_index

    def remove_active(self) -> None:
        if len(self.layers) == 1:
            self.active.mask.fill(0)
            self.active.protect = False
            self.active.name = "Fill 1"
            return
        self.layers.pop(self.active_index)
        self.active_index = min(self.active_index, len(self.layers) - 1)

    def set_active(self, index: int) -> None:
        if not 0 <= int(index) < len(self.layers):
            raise IndexError("mask layer index out of range")
        self.active_index = int(index)

    def set_active_protect(self, protect: bool) -> None:
        self.active.protect = bool(protect)

    def fill_mask(self) -> np.ndarray:
        out = np.zeros((self.height, self.width), dtype=np.uint8)
        for layer in self.layers:
            if layer.visible and not layer.protect:
                np.maximum(out, layer.mask, out=out)
        return out

    def protect_mask(self) -> np.ndarray:
        out = np.zeros((self.height, self.width), dtype=np.uint8)
        for layer in self.layers:
            if layer.visible and layer.protect:
                np.maximum(out, layer.mask, out=out)
        return out

    def composite(self) -> np.ndarray:
        fill = self.fill_mask()
        protect = self.protect_mask()
        return cv2.subtract(fill, protect)

    def clear_active(self) -> None:
        self.active.mask.fill(0)

    def clear_all(self) -> None:
        for layer in self.layers:
            layer.mask.fill(0)

    def invert_active(self) -> None:
        self.active.mask[:] = 255 - self.active.mask

    def transform_active(
        self,
        operation: str,
        *,
        radius: int = 3,
        guide_rgba: np.ndarray | None = None,
    ) -> None:
        radius = max(1, int(radius))
        mask = self.active.mask
        if operation == "feather":
            sigma = max(0.5, radius / 2.0)
            self.active.mask[:] = cv2.GaussianBlur(mask, (0, 0), sigmaX=sigma, sigmaY=sigma)
        elif operation == "smooth":
            size = radius * 2 + 1
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
            opened = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            self.active.mask[:] = cv2.morphologyEx(opened, cv2.MORPH_CLOSE, kernel)
        elif operation in {"grow", "shrink"}:
            size = radius * 2 + 1
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
            fn = cv2.dilate if operation == "grow" else cv2.erode
            self.active.mask[:] = fn(mask, kernel, iterations=1)
        elif operation == "edge":
            if guide_rgba is None:
                self.transform_active("smooth", radius=radius)
            else:
                self.active.mask[:] = guided_refine(mask, guide_rgba, radius)
        else:
            raise ValueError(f"unknown mask operation: {operation}")

    def save(self, path: str | Path) -> None:
        path = Path(path)
        masks = np.stack([layer.mask for layer in self.layers], axis=0)
        np.savez_compressed(
            path,
            version=np.array([1], dtype=np.uint8),
            masks=masks,
            names=np.asarray([layer.name for layer in self.layers]),
            visible=np.asarray([layer.visible for layer in self.layers], dtype=np.bool_),
            protect=np.asarray([layer.protect for layer in self.layers], dtype=np.bool_),
            active=np.asarray([self.active_index], dtype=np.int32),
        )

    @classmethod
    def load(cls, path: str | Path) -> "MaskLayerStack":
        with np.load(Path(path), allow_pickle=False) as data:
            masks = np.asarray(data["masks"], dtype=np.uint8)
            if masks.ndim != 3 or masks.shape[0] < 1:
                raise ValueError("mask project contains no layers")
            stack = cls(masks.shape[2], masks.shape[1])
            names = [str(value) for value in data["names"].tolist()]
            visible = np.asarray(data["visible"], dtype=np.bool_)
            protect = np.asarray(data["protect"], dtype=np.bool_)
            layers = [
                MaskLayer(
                    names[i] if i < len(names) else f"Layer {i + 1}",
                    masks[i].copy(),
                    bool(visible[i]) if i < len(visible) else True,
                    bool(protect[i]) if i < len(protect) else False,
                )
                for i in range(masks.shape[0])
            ]
            active = int(np.asarray(data["active"]).reshape(-1)[0])
            stack.restore(layers, active)
            return stack


def guided_refine(mask: np.ndarray, guide_rgba: np.ndarray, radius: int) -> np.ndarray:
    """Small guided filter that smooths a mask without crossing image edges."""
    guide = np.asarray(guide_rgba)
    if guide.ndim == 3:
        rgb = guide[:, :, :3].astype(np.float32) / 255.0
        guide_f = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    else:
        guide_f = guide.astype(np.float32) / 255.0
    source = mask.astype(np.float32) / 255.0
    win = max(1, int(radius))
    size = (win * 2 + 1, win * 2 + 1)
    mean_i = cv2.boxFilter(guide_f, -1, size, normalize=True)
    mean_p = cv2.boxFilter(source, -1, size, normalize=True)
    corr_i = cv2.boxFilter(guide_f * guide_f, -1, size, normalize=True)
    corr_ip = cv2.boxFilter(guide_f * source, -1, size, normalize=True)
    var_i = corr_i - mean_i * mean_i
    cov_ip = corr_ip - mean_i * mean_p
    a = cov_ip / (var_i + 1e-3)
    b = mean_p - a * mean_i
    mean_a = cv2.boxFilter(a, -1, size, normalize=True)
    mean_b = cv2.boxFilter(b, -1, size, normalize=True)
    refined = mean_a * guide_f + mean_b
    return np.clip(refined * 255.0, 0, 255).astype(np.uint8)


def mask_roi(
    mask: np.ndarray,
    *,
    padding: int = 96,
    align: int = 8,
) -> tuple[int, int, int, int] | None:
    """Return an expanded, aligned (left, top, right, bottom) nonzero ROI."""
    ys, xs = np.nonzero(mask > 0)
    if xs.size == 0:
        return None
    h, w = mask.shape[:2]
    pad = max(0, int(padding))
    left = max(0, int(xs.min()) - pad)
    top = max(0, int(ys.min()) - pad)
    right = min(w, int(xs.max()) + 1 + pad)
    bottom = min(h, int(ys.max()) + 1 + pad)
    unit = max(1, int(align))
    left = max(0, (left // unit) * unit)
    top = max(0, (top // unit) * unit)
    right = min(w, ((right + unit - 1) // unit) * unit)
    bottom = min(h, ((bottom + unit - 1) // unit) * unit)
    return left, top, right, bottom
