"""Standalone entry point executed inside Lluna's isolated SAM 3.1 environment.

SAM 3's `Sam3Processor` (image) supports text prompts (`set_text_prompt`) and
box/geometric prompts (`add_geometric_prompt`) but has no point-click
primitive. A click point is approximated here as a small box centered on the
click, the closest supported primitive - not pixel-identical to true
point-conditioned segmentation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _to_numpy(value):
    try:
        import torch

        if isinstance(value, torch.Tensor):
            return value.detach().cpu().numpy()
    except ImportError:
        pass
    import numpy as np

    return np.asarray(value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    args = parser.parse_args()
    request = json.loads(Path(args.request).read_text(encoding="utf-8"))

    import numpy as np
    from PIL import Image

    from sam3.model.sam3_image_processor import Sam3Processor
    from sam3.model_builder import build_sam3_image_model

    model = build_sam3_image_model(
        checkpoint_path=request["checkpoint_path"],
        load_from_HF=False,
        device=request.get("device") or "cpu",
    )
    processor = Sam3Processor(model)

    image = Image.open(request["input_path"]).convert("RGB")
    state = processor.set_image(image)

    confidence_threshold = request.get("confidence_threshold")
    if confidence_threshold is not None and hasattr(processor, "set_confidence_threshold"):
        processor.set_confidence_threshold(float(confidence_threshold), state=state)

    text = str(request.get("text") or "").strip()
    points = request.get("points") or []
    if text:
        output = processor.set_text_prompt(prompt=text, state=state)
    elif points:
        width, height = image.size
        click_x, click_y = float(points[0][0]), float(points[0][1])
        half = max(4.0, 0.03 * min(width, height))
        box = [
            click_x / width,
            click_y / height,
            (2 * half) / width,
            (2 * half) / height,
        ]
        output = processor.add_geometric_prompt(box=box, label=True, state=state)
    else:
        raise ValueError("SAM 3.1 needs a text prompt or a click point.")

    masks = output.get("masks")
    if masks is None or len(masks) == 0:
        raise RuntimeError("SAM 3.1 did not find a matching object.")
    scores = output.get("scores")
    scores_arr = _to_numpy(scores) if scores is not None else None
    best = int(np.argmax(scores_arr)) if scores_arr is not None and len(scores_arr) else 0

    mask = _to_numpy(masks[best])
    if mask.ndim > 2:
        mask = mask.squeeze()
    mask_threshold_value = request.get("mask_threshold")
    mask_threshold = float(mask_threshold_value) if mask_threshold_value is not None else 0.5
    mask_image = ((mask > mask_threshold).astype(np.uint8)) * 255
    Image.fromarray(mask_image, mode="L").save(request["output_mask_path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
