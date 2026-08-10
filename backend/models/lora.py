"""Composing LoRA adapters onto a base diffusion pipeline.

A LoRA is a small set of low-rank weight deltas trained against one specific base
model. It is not a model you can run: it only means anything applied on top of the
base it was trained for. That shapes everything here.

* **Selection is user data.** LoRAs arrive as custom models the user imported, so a
  selection is validated at run time - installed, enabled, actually a LoRA, and
  trained for the base model in the node - and refused with a readable reason
  otherwise, rather than producing quietly wrong images.
* **Composition is temporary.** Pipelines are cached between runs, so adapters are
  applied before generation and unloaded after. Baking them into a cached pipeline
  would leak one run's LoRAs into the next run that asked for none, and keying the
  pipeline cache by LoRA set instead would multiply resident models in VRAM.

Several LoRAs can apply at once, each with its own weight, which is how style and
subject adapters are normally combined.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from backend.models.conditioning import base_matches

# Adapter names must be unique per pipeline and are how diffusers addresses each
# set of weights in set_adapters(); the model id is unique already.
_MAX_ACTIVE = 8


class LoraError(RuntimeError):
    """A LoRA selection cannot be honoured."""


@dataclass(frozen=True)
class LoraSelection:
    """What the user asked for: a custom model id and how strongly to apply it."""

    model_id: str
    weight: float = 1.0

    @classmethod
    def from_mapping(cls, raw: Any) -> "LoraSelection":
        if isinstance(raw, str):
            return cls(model_id=raw)
        if not isinstance(raw, dict):
            raise LoraError("Each LoRA must be a model id or an object with modelId and weight.")
        model_id = str(raw.get("modelId") or raw.get("model_id") or raw.get("id") or "").strip()
        if not model_id:
            raise LoraError("A LoRA selection is missing its modelId.")
        weight = raw.get("weight", raw.get("strength", 1.0))
        try:
            weight = float(weight)
        except (TypeError, ValueError) as exc:
            raise LoraError(f"LoRA {model_id!r} has a non-numeric weight.") from exc
        return cls(model_id=model_id, weight=weight)


@dataclass(frozen=True)
class ResolvedLora:
    selection: LoraSelection
    path: Path
    adapter_name: str
    weight_name: str | None = None


def parse_selections(raw: Any) -> tuple[LoraSelection, ...]:
    """Normalize whatever the node sent into selections, preserving order."""
    if not raw:
        return ()
    if isinstance(raw, (str, dict)):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        raise LoraError("LoRAs must be given as a list.")
    selections = tuple(LoraSelection.from_mapping(item) for item in raw)
    if len(selections) > _MAX_ACTIVE:
        raise LoraError(f"At most {_MAX_ACTIVE} LoRAs can be applied at once.")
    seen: set[str] = set()
    for selection in selections:
        if selection.model_id in seen:
            raise LoraError(f"LoRA {selection.model_id!r} was selected twice.")
        seen.add(selection.model_id)
    return selections


def resolve_selections(
    selections: Sequence[LoraSelection], *, base_model_id: str = ""
) -> tuple[ResolvedLora, ...]:
    """Turn selections into on-disk adapters, refusing anything unusable."""
    if not selections:
        return ()
    from backend.models.dynamic_registry import DynamicModelRegistry

    registry = DynamicModelRegistry.instance()
    resolved: list[ResolvedLora] = []
    for selection in selections:
        model_id = selection.model_id.removeprefix("custom:")
        try:
            record = registry.get(model_id)
        except KeyError as exc:
            raise LoraError(f"LoRA {model_id!r} is not installed.") from exc
        if not record.installed:
            raise LoraError(f"LoRA {record.manifest.name!r} is not installed.")
        if not record.enabled:
            raise LoraError(f"LoRA {record.manifest.name!r} is installed but not enabled.")
        if record.manifest.variant.kind != "lora":
            raise LoraError(
                f"{record.manifest.name!r} is a {record.manifest.variant.kind} model, not a LoRA."
            )
        declared_base = str(record.manifest.variant.base_model or "")
        if not base_matches(declared_base, base_model_id):
            raise LoraError(
                f"LoRA {record.manifest.name!r} was trained for {declared_base!r}, "
                f"which is not the model this node is running ({base_model_id!r})."
            )
        weight_name = next(
            (name for name in record.manifest.expected_files if name.endswith(".safetensors")),
            None,
        )
        resolved.append(
            ResolvedLora(
                selection=selection,
                path=record.path,
                adapter_name=model_id.replace(":", "_").replace("/", "_"),
                weight_name=weight_name,
            )
        )
    return tuple(resolved)


def selection_signature(selections: Iterable[LoraSelection]) -> str:
    """Stable description of a selection, for cache keys and logs."""
    return ",".join(f"{item.model_id}@{item.weight:g}" for item in selections)


@contextmanager
def applied(pipeline: Any, resolved: Sequence[ResolvedLora]) -> Iterator[Any]:
    """Apply LoRAs for the duration of the block, then remove them.

    Unloading in a ``finally`` is what keeps the shared pipeline cache honest:
    the next generation starts from the base weights whatever happened here,
    including when generation raised or was cancelled.
    """
    if not resolved:
        yield pipeline
        return
    if not hasattr(pipeline, "load_lora_weights"):
        raise LoraError("This model's pipeline does not support LoRA adapters.")
    try:
        for item in resolved:
            kwargs = {"adapter_name": item.adapter_name}
            if item.weight_name:
                kwargs["weight_name"] = item.weight_name
            try:
                pipeline.load_lora_weights(str(item.path), **kwargs)
            except Exception as exc:  # diffusers raises a wide range here
                raise LoraError(
                    f"LoRA {item.selection.model_id!r} could not be loaded: {exc}"
                ) from exc
        names = [item.adapter_name for item in resolved]
        weights = [float(item.selection.weight) for item in resolved]
        try:
            pipeline.set_adapters(names, adapter_weights=weights)
        except Exception as exc:
            raise LoraError(f"LoRA weights could not be combined: {exc}") from exc
        yield pipeline
    finally:
        try:
            pipeline.unload_lora_weights()
        except Exception:
            # A pipeline that cannot unload is not reusable; the caller's cache
            # eviction is the backstop, and hiding this would mask the real error
            # when generation itself failed.
            pass
