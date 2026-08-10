"""Shared rules for models that condition another model rather than run alone.

LoRAs and ControlNets are both *attachments*: trained against one base model, and
meaningless without it. They differ in how they attach — a LoRA is merged into the
weights at call time, a ControlNet is a second network the pipeline consults — but
they share the question that decides whether a pairing is legal at all, which is
what lives here.
"""

from __future__ import annotations


class ConditioningError(RuntimeError):
    """A conditioning model cannot be attached to the requested base."""


def base_matches(declared: str, base_model_id: str) -> bool:
    """Whether an attachment's declared base matches the base actually running.

    Compared leniently on purpose: an upstream model card names its own repo
    ("black-forest-labs/FLUX.1-dev") while a node names Lluna's model id
    ("flux"), and refusing that mismatch outright would reject correct pairings
    that users would have no way to fix. An empty declaration cannot be checked
    and is allowed through — the manifest layer already requires one for models
    that have been reviewed.

    A genuinely wrong pairing (an SDXL adapter on FLUX) still fails, which is the
    case that matters: it is the one that produces quietly wrong images instead
    of an error.
    """
    if not declared or not base_model_id:
        return True
    left = declared.strip().lower().replace("_", "-")
    right = base_model_id.strip().lower().replace("_", "-").removeprefix("custom:")
    if left == right:
        return True
    tail = left.rsplit("/", 1)[-1]
    return tail == right or right in tail or tail in right
