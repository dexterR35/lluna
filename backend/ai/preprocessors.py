"""Turning a source image into a control map for ControlNet.

These are the "OPTIONAL CONTROL" leg of the graph: a source image goes in, a
structural hint comes out — edges, a depth field, a skeleton — which a ControlNet
then uses to steer generation.

Preprocessors are independent capabilities, not dependencies of any generation
model. Three routes produce the same kind of artifact and are interchangeable:

* **Built in.** Canny edge detection is pure OpenCV, which Lluna already ships, so
  it needs no download and is always available.
* **Installed on demand.** Depth and pose need their own small models, so they are
  ordinary catalog entries the user installs only if they want them. Until then
  the node explains exactly what to install rather than failing obscurely.
* **Supplied by the user.** A control map made elsewhere is just an image, and can
  be wired straight into a ControlNet input without any preprocessor at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from PIL import Image


class PreprocessorError(RuntimeError):
    """A control map could not be produced."""


@dataclass(frozen=True)
class Preprocessor:
    id: str
    label: str
    description: str
    # Empty means "no download needed"; otherwise the model id the user installs.
    required_model: str = ""

    @property
    def built_in(self) -> bool:
        return not self.required_model


PREPROCESSORS: dict[str, Preprocessor] = {
    item.id: item
    for item in (
        Preprocessor(
            "canny",
            "Canny edges",
            "Edge outlines. Built in, no download, best for preserving composition.",
        ),
        Preprocessor(
            "depth",
            "Depth map",
            "Relative distance per pixel. Best for preserving 3D layout.",
            required_model="depth-anything-v2-small",
        ),
        Preprocessor(
            "pose",
            "Human pose",
            "Body keypoint skeleton. Best for preserving a figure's posture.",
            required_model="dwpose",
        ),
    )
}


def available() -> tuple[dict[str, Any], ...]:
    """Every preprocessor with whether it can run right now."""
    return tuple(
        {
            "id": item.id,
            "label": item.label,
            "description": item.description,
            "builtIn": item.built_in,
            "requiredModel": item.required_model,
            "ready": item.built_in or _model_installed(item.required_model),
        }
        for item in PREPROCESSORS.values()
    )


def _model_installed(model_id: str) -> bool:
    if not model_id:
        return True
    try:
        from backend.models.dynamic_registry import DynamicModelRegistry

        record = DynamicModelRegistry.instance().get(model_id)
        return bool(record.installed and record.enabled)
    except (ImportError, KeyError, OSError):
        return False


def canny(image: Image.Image, *, low: int = 100, high: int = 200) -> Image.Image:
    """Edge map via OpenCV. No model, no download, runs anywhere.

    Thresholds are the standard hysteresis pair: pixels above ``high`` start an
    edge, pixels above ``low`` continue one. Wider gaps keep more detail.
    """
    import cv2
    import numpy as np

    if low < 0 or high < 0:
        raise PreprocessorError("Canny thresholds cannot be negative.")
    if low >= high:
        raise PreprocessorError(
            f"The low threshold ({low}) must be below the high threshold ({high})."
        )
    array = np.array(image.convert("RGB"))
    edges = cv2.Canny(array, int(low), int(high))
    # ControlNet expects a 3-channel image, and the convention is white edges on
    # black, which is what cv2.Canny already produces.
    return Image.fromarray(np.stack([edges] * 3, axis=-1))


def _depth(image: Image.Image, **_params: Any) -> Image.Image:
    raise PreprocessorError(
        "Depth maps need the Depth Anything V2 model. Install it from "
        "Settings -> Models, or wire in a depth map you made elsewhere."
    )


def _pose(image: Image.Image, **_params: Any) -> Image.Image:
    raise PreprocessorError(
        "Pose maps need the DWPose model. Install it from Settings -> Models, "
        "or wire in a pose map you made elsewhere."
    )


_RUNNERS: dict[str, Callable[..., Image.Image]] = {
    "canny": canny,
    "depth": _depth,
    "pose": _pose,
}


def run(kind: str, image: Image.Image, **params: Any) -> Image.Image:
    """Produce a control map of type ``kind`` from ``image``."""
    name = str(kind or "").strip().lower()
    if name not in PREPROCESSORS:
        raise PreprocessorError(
            f"Unknown control map {kind!r}. Available: {', '.join(sorted(PREPROCESSORS))}."
        )
    if not isinstance(image, Image.Image):
        raise PreprocessorError("A control map needs a source image.")
    return _RUNNERS[name](image, **params)
