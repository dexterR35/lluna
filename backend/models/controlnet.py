"""Composing ControlNet conditioning onto a base diffusion pipeline.

A ControlNet differs from a LoRA in *how* it attaches, and that difference drives
this module. A LoRA merges deltas into weights the pipeline already has, so it can
be switched on and off around a call. A ControlNet is a second network the sampler
consults at every step, so the pipeline itself must be a ControlNet-aware class —
`StableDiffusionXLControlNetPipeline`, `FluxControlNetPipeline`, and so on.

Rebuilding that pipeline from disk would mean loading the base model twice. Instead
this uses diffusers' `from_pipe`, which constructs the new pipeline class **around
the components already resident** — same VAE, same text encoders, same transformer,
no extra VRAM for the base. The ControlNet weights are the only new load, and the
composed view is discarded afterwards so the cached base pipeline is untouched.

Compatibility is not a detail here: a ControlNet trained for SDXL consulted by a
FLUX sampler does not error, it produces noise. `base_matches` is what prevents it.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from PIL import Image

from backend.models.conditioning import base_matches

# More than a couple of ControlNets at once is rarely useful and multiplies both
# VRAM and the chance of them fighting each other.
_MAX_ACTIVE = 4


class ControlNetError(RuntimeError):
    """A ControlNet selection cannot be honoured."""


@dataclass(frozen=True)
class ControlSelection:
    """One ControlNet, its control image, and how it is scheduled.

    ``start``/``end`` are fractions of the sampling run: 0.0-1.0 means "guide the
    whole way", 0.0-0.5 means "shape the composition early, then let the model
    finish freely", which is how structure is imposed without flattening detail.
    """

    model_id: str
    strength: float = 1.0
    start: float = 0.0
    end: float = 1.0
    image: Image.Image | None = None

    @classmethod
    def from_mapping(cls, raw: Any) -> "ControlSelection":
        if isinstance(raw, str):
            return cls(model_id=raw)
        if not isinstance(raw, dict):
            raise ControlNetError(
                "Each ControlNet must be a model id or an object with modelId."
            )
        model_id = str(raw.get("modelId") or raw.get("model_id") or raw.get("id") or "").strip()
        if not model_id:
            raise ControlNetError("A ControlNet selection is missing its modelId.")

        def number(key: str, fallback: float) -> float:
            value = raw.get(key, fallback)
            try:
                return float(value)
            except (TypeError, ValueError) as exc:
                raise ControlNetError(
                    f"ControlNet {model_id!r} has a non-numeric {key}."
                ) from exc

        strength = number("strength", raw.get("weight", 1.0))
        start = number("start", 0.0)
        end = number("end", 1.0)
        if not 0.0 <= start < end <= 1.0:
            raise ControlNetError(
                f"ControlNet {model_id!r} needs 0 <= start < end <= 1; got {start} to {end}."
            )
        return cls(
            model_id=model_id,
            strength=strength,
            start=start,
            end=end,
            image=raw.get("image"),
        )


@dataclass(frozen=True)
class ResolvedControlNet:
    selection: ControlSelection
    path: Path
    name: str


def parse_selections(raw: Any) -> tuple[ControlSelection, ...]:
    if not raw:
        return ()
    if isinstance(raw, (str, dict)):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        raise ControlNetError("ControlNets must be given as a list.")
    selections = tuple(ControlSelection.from_mapping(item) for item in raw)
    if len(selections) > _MAX_ACTIVE:
        raise ControlNetError(f"At most {_MAX_ACTIVE} ControlNets can be applied at once.")
    seen: set[str] = set()
    for selection in selections:
        if selection.model_id in seen:
            raise ControlNetError(f"ControlNet {selection.model_id!r} was selected twice.")
        seen.add(selection.model_id)
    return selections


def resolve_selections(
    selections: Sequence[ControlSelection], *, base_model_id: str = ""
) -> tuple[ResolvedControlNet, ...]:
    """Validate selections against what is installed and what the base model is."""
    if not selections:
        return ()
    from backend.models.dynamic_registry import DynamicModelRegistry

    registry = DynamicModelRegistry.instance()
    resolved: list[ResolvedControlNet] = []
    for selection in selections:
        model_id = selection.model_id.removeprefix("custom:")
        try:
            record = registry.get(model_id)
        except KeyError as exc:
            raise ControlNetError(f"ControlNet {model_id!r} is not installed.") from exc
        if not record.installed:
            raise ControlNetError(f"ControlNet {record.manifest.name!r} is not installed.")
        if not record.enabled:
            raise ControlNetError(
                f"ControlNet {record.manifest.name!r} is installed but not enabled."
            )
        if record.manifest.variant.kind != "controlnet":
            raise ControlNetError(
                f"{record.manifest.name!r} is a {record.manifest.variant.kind} model, "
                "not a ControlNet."
            )
        declared_base = str(record.manifest.variant.base_model or "")
        if not base_matches(declared_base, base_model_id):
            raise ControlNetError(
                f"ControlNet {record.manifest.name!r} was trained for {declared_base!r}, "
                f"which is not the model this node is running ({base_model_id!r}). "
                "Mismatched ControlNets produce noise rather than an error."
            )
        if selection.image is None:
            raise ControlNetError(
                f"ControlNet {record.manifest.name!r} has no control image. Connect a "
                "Control Map node, or an image you prepared yourself."
            )
        resolved.append(
            ResolvedControlNet(selection=selection, path=record.path, name=model_id)
        )
    return tuple(resolved)


def selection_signature(selections: Iterable[ControlSelection]) -> str:
    return ",".join(
        f"{item.model_id}@{item.strength:g}[{item.start:g}-{item.end:g}]" for item in selections
    )


def call_kwargs(resolved: Sequence[ResolvedControlNet]) -> dict[str, Any]:
    """Pipeline call arguments for a resolved selection.

    diffusers takes bare values for a single ControlNet and lists for several,
    so single selections are unwrapped rather than passed as one-item lists.
    """
    if not resolved:
        return {}
    images = [item.selection.image for item in resolved]
    scales = [float(item.selection.strength) for item in resolved]
    starts = [float(item.selection.start) for item in resolved]
    ends = [float(item.selection.end) for item in resolved]
    if len(resolved) == 1:
        return {
            "control_image": images[0],
            "controlnet_conditioning_scale": scales[0],
            "control_guidance_start": starts[0],
            "control_guidance_end": ends[0],
        }
    return {
        "control_image": images,
        "controlnet_conditioning_scale": scales,
        "control_guidance_start": starts,
        "control_guidance_end": ends,
    }


def _load_models(resolved: Sequence[ResolvedControlNet]) -> Any:
    from diffusers import ControlNetModel

    models = []
    for item in resolved:
        try:
            models.append(ControlNetModel.from_pretrained(str(item.path), local_files_only=True))
        except Exception as exc:
            raise ControlNetError(
                f"ControlNet {item.selection.model_id!r} could not be loaded: {exc}"
            ) from exc
    return models[0] if len(models) == 1 else models


@contextmanager
def composed(pipeline: Any, resolved: Sequence[ResolvedControlNet]) -> Iterator[Any]:
    """Yield a ControlNet-aware view of ``pipeline`` for the duration of the block.

    The base pipeline is left exactly as it was: `from_pipe` shares its components
    rather than copying them, and the composed view is dropped on exit, so the
    cached base is reusable by the next run whatever happens here.
    """
    if not resolved:
        yield pipeline
        return
    try:
        from diffusers import AutoPipelineForText2Image
    except ImportError as exc:
        raise ControlNetError(
            "This diffusers version does not support ControlNet composition."
        ) from exc

    controlnet = _load_models(resolved)
    try:
        composed_pipeline = AutoPipelineForText2Image.from_pipe(pipeline, controlnet=controlnet)
    except Exception as exc:
        raise ControlNetError(
            f"This model does not accept ControlNet conditioning: {exc}"
        ) from exc
    try:
        yield composed_pipeline
    finally:
        del composed_pipeline
        del controlnet
