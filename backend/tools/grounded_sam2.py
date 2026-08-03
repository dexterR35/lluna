"""Lazy SAM2 + Grounding DINO segmentation for Select Object (on-demand load/unload)."""

from __future__ import annotations

import gc
import threading
from typing import List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image

from backend.tools.constant import SelectObjectModelId
from backend.tools.select_object_models import (
    local_repo_path,
    resolve_pair,
)

_infer_lock = threading.RLock()
_sam2_model = None
_sam2_processor = None
_dino_model = None
_dino_processor = None
_loaded_sam2_id: Optional[SelectObjectModelId] = None
_loaded_dino_id: Optional[SelectObjectModelId] = None


def _device():
    import torch

    from backend.configuration.service import get_settings
    from backend.tools.hardware_accelerator import HardwareAccelerator

    hw = HardwareAccelerator.instance()
    hw.set_enabled(bool(get_settings().subtitle.hardware_acceleration))
    dev = hw.device
    if dev.type == "cuda" and not torch.cuda.is_available():
        return torch.device("cpu")
    return dev


def release_select_object_models(blocking: bool = True, timeout: float = 8.0) -> bool:
    global _sam2_model, _sam2_processor, _dino_model, _dino_processor
    global _loaded_sam2_id, _loaded_dino_id

    got = _infer_lock.acquire(blocking=blocking, timeout=timeout if blocking else 0)
    if not got:
        return False
    try:
        for name in ("_sam2_model", "_sam2_processor", "_dino_model", "_dino_processor"):
            obj = globals().get(name)
            if obj is not None:
                try:
                    if hasattr(obj, "cpu"):
                        obj.cpu()
                except Exception:
                    pass
        _sam2_model = None
        _sam2_processor = None
        _dino_model = None
        _dino_processor = None
        _loaded_sam2_id = None
        _loaded_dino_id = None
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
        return True
    finally:
        _infer_lock.release()


def _unload_sam2_only() -> None:
    global _sam2_model, _sam2_processor, _loaded_sam2_id
    if _sam2_model is not None:
        try:
            _sam2_model.cpu()
        except Exception:
            pass
    _sam2_model = None
    _sam2_processor = None
    _loaded_sam2_id = None


def _unload_dino_only() -> None:
    global _dino_model, _dino_processor, _loaded_dino_id
    if _dino_model is not None:
        try:
            _dino_model.cpu()
        except Exception:
            pass
    _dino_model = None
    _dino_processor = None
    _loaded_dino_id = None


def _load_sam2(model_id: SelectObjectModelId):
    global _sam2_model, _sam2_processor, _loaded_sam2_id
    if _sam2_model is not None and _loaded_sam2_id == model_id:
        return _sam2_model, _sam2_processor

    if _loaded_sam2_id != model_id:
        _unload_sam2_only()
    try:
        from transformers import Sam2Model, Sam2Processor
    except ImportError as e:
        raise RuntimeError(
            "transformers is required for Select Object (SAM2). "
            "Restart the app after running: python -m pip install -r requirements.txt"
        ) from e

    import logging

    path = str(local_repo_path(model_id))
    device = _device()
    _sam2_processor = Sam2Processor.from_pretrained(path)

    # HF repos (e.g. facebook/sam2-hiera-tiny) store config model_type=sam2_video, but
    # still-image click/box segmentation uses Sam2Model per official transformers docs.
    class _Sam2CheckpointTypeFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            return "model of type" not in record.getMessage()

    tf_log = logging.getLogger("transformers")
    load_filter = _Sam2CheckpointTypeFilter()
    tf_log.addFilter(load_filter)
    try:
        _sam2_model = Sam2Model.from_pretrained(path).to(device)
    finally:
        tf_log.removeFilter(load_filter)

    _sam2_model.eval()
    _loaded_sam2_id = model_id
    return _sam2_model, _sam2_processor


def _load_dino(model_id: SelectObjectModelId):
    global _dino_model, _dino_processor, _loaded_dino_id
    if _dino_model is not None and _loaded_dino_id == model_id:
        return _dino_model, _dino_processor

    if _loaded_dino_id != model_id:
        _unload_dino_only()
    try:
        from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor
    except ImportError as e:
        raise RuntimeError(
            "transformers is required for Select Object (Grounding DINO). "
            "Restart the app after running: python -m pip install -r requirements.txt"
        ) from e

    path = str(local_repo_path(model_id))
    device = _device()
    _dino_processor = AutoProcessor.from_pretrained(path)
    _dino_model = AutoModelForZeroShotObjectDetection.from_pretrained(path).to(device)
    _dino_model.eval()
    _loaded_dino_id = model_id
    return _dino_model, _dino_processor


def select_object_models_ready(
    sam2_id: SelectObjectModelId,
    dino_id: SelectObjectModelId,
    *,
    need_dino: bool,
) -> bool:
    """True when cached weights match the pair this job will use (no reload needed)."""
    sam2_ready = _sam2_model is not None and _loaded_sam2_id == sam2_id
    if not need_dino:
        return sam2_ready
    dino_ready = _dino_model is not None and _loaded_dino_id == dino_id
    return sam2_ready and dino_ready


def _pick_best_mask(masks, scores) -> np.ndarray:
    """Return HxW uint8 mask from SAM2 outputs."""
    if masks is None:
        raise RuntimeError("SAM2 returned no masks.")
    m = masks
    if hasattr(m, "detach"):
        m = m.detach().cpu().numpy()
    else:
        m = np.asarray(m)
    s = scores
    if hasattr(s, "detach"):
        s = s.detach().cpu().numpy()
    else:
        s = np.asarray(s)

    # shapes: (num_masks, H, W) or (1, num_masks, H, W)
    while m.ndim > 3:
        m = m[0]
    while s.ndim > 1:
        s = s.reshape(-1)

    if m.ndim == 2:
        best = m
    else:
        idx = int(np.argmax(s)) if s.size else 0
        best = m[idx]

    return (best > 0).astype(np.uint8) * 255


def _segment_points_sam2(
    image: Image.Image,
    points: Sequence[Tuple[int, int]],
    labels: Sequence[int],
    sam2_id: SelectObjectModelId,
) -> np.ndarray:
    import torch

    if not points:
        raise ValueError("Click Select Object requires at least one point.")

    model, processor = _load_sam2(sam2_id)
    device = _device()
    rgb = image.convert("RGB")

    # [image, object, point, [x, y]] — transformers 5.x Sam2Processor format
    coord_points = [[float(x), float(y)] for x, y in points]
    input_points = [[coord_points]]
    input_labels = [[[int(v) for v in labels]]]

    inputs = processor(
        rgb,
        input_points=input_points,
        input_labels=input_labels,
        return_tensors="pt",
    )
    inputs = {k: v.to(device) if hasattr(v, "to") else v for k, v in inputs.items()}

    with torch.no_grad():
        outputs = model(**inputs)

    masks = processor.post_process_masks(
        outputs.pred_masks.cpu(),
        inputs["original_sizes"],
    )[0]
    scores = outputs.iou_scores.cpu() if hasattr(outputs, "iou_scores") else None
    return _pick_best_mask(masks, scores)


def _dino_boxes(
    image: Image.Image,
    text: str,
    dino_id: SelectObjectModelId,
    box_threshold: float,
    text_threshold: float,
) -> List[List[float]]:
    import torch

    phrase = (text or "").strip()
    if not phrase:
        return []

    model, processor = _load_dino(dino_id)
    device = _device()
    rgb = image.convert("RGB")

    inputs = processor(images=rgb, text=phrase, return_tensors="pt")
    inputs = {k: v.to(device) if hasattr(v, "to") else v for k, v in inputs.items()}

    with torch.no_grad():
        outputs = model(**inputs)

    target = [rgb.size[::-1]]  # (h, w)
    post_kwargs = dict(
        outputs=outputs,
        input_ids=inputs["input_ids"],
        text_threshold=text_threshold,
        target_sizes=target,
    )
    # transformers 5.x: threshold; older HF builds used box_threshold
    try:
        results = processor.post_process_grounded_object_detection(
            **post_kwargs,
            threshold=box_threshold,
        )
    except TypeError:
        results = processor.post_process_grounded_object_detection(
            **post_kwargs,
            box_threshold=box_threshold,
        )
    if not results:
        return []
    boxes = results[0].get("boxes")
    if boxes is None:
        return []
    if hasattr(boxes, "detach"):
        boxes = boxes.detach().cpu().tolist()
    return [list(map(float, b)) for b in boxes]


def _segment_boxes_sam2(
    image: Image.Image,
    boxes: List[List[float]],
    sam2_id: SelectObjectModelId,
) -> np.ndarray:
    import torch

    if not boxes:
        raise RuntimeError("No object boxes detected for that text.")

    model, processor = _load_sam2(sam2_id)
    device = _device()
    rgb = image.convert("RGB")
    w, h = rgb.size

    union = np.zeros((h, w), dtype=np.uint8)
    for box in boxes:
        x0, y0, x1, y1 = box
        x0 = max(0.0, min(float(x0), w - 1))
        x1 = max(0.0, min(float(x1), w - 1))
        y0 = max(0.0, min(float(y0), h - 1))
        y1 = max(0.0, min(float(y1), h - 1))
        if x1 <= x0 or y1 <= y0:
            continue
        input_boxes = [[[x0, y0, x1, y1]]]
        inputs = processor(rgb, input_boxes=input_boxes, return_tensors="pt")
        inputs = {k: v.to(device) if hasattr(v, "to") else v for k, v in inputs.items()}
        with torch.no_grad():
            outputs = model(**inputs)
        masks = processor.post_process_masks(
            outputs.pred_masks.cpu(),
            inputs["original_sizes"],
        )[0]
        scores = outputs.iou_scores.cpu() if hasattr(outputs, "iou_scores") else None
        m = _pick_best_mask(masks, scores)
        union = np.maximum(union, m)

    if not np.any(union):
        raise RuntimeError("SAM2 could not build a mask from detected boxes.")
    return union


def run_select_object(
    image_path: str,
    output_mask_path: str,
    *,
    points: Optional[Sequence[Sequence[float]]] = None,
    labels: Optional[Sequence[int]] = None,
    text: Optional[str] = None,
    box_threshold: float = 0.25,
    text_threshold: float = 0.25,
    more_complex: bool | None = None,
) -> str:
    """
    Produce an L-mode mask PNG. Loads models for this call only (caller may release after).
    """
    with _infer_lock:
        sam2_id, dino_id = resolve_pair(more_complex)
        image = Image.open(image_path).convert("RGB")

        pts: List[Tuple[int, int]] = []
        lbls: List[int] = []
        if points:
            for i, p in enumerate(points):
                if len(p) < 2:
                    continue
                pts.append((int(round(p[0])), int(round(p[1]))))
                if labels and i < len(labels):
                    lbls.append(int(labels[i]))
                else:
                    lbls.append(1)

        phrase = (text or "").strip()
        mask: np.ndarray | None = None

        if phrase:
            boxes = _dino_boxes(image, phrase, dino_id, box_threshold, text_threshold)
            if boxes:
                if pts:
                    # Prefer box nearest click when both provided
                    cx, cy = pts[0]
                    def _dist(b):
                        bx0, by0, bx1, by1 = b
                        mx, my = (bx0 + bx1) / 2, (by0 + by1) / 2
                        return (mx - cx) ** 2 + (my - cy) ** 2
                    boxes = [min(boxes, key=_dist)]
                mask = _segment_boxes_sam2(image, boxes, sam2_id)
            elif pts:
                mask = _segment_points_sam2(image, pts, lbls, sam2_id)
            else:
                raise RuntimeError(f"No object found for: {phrase}")
        elif pts:
            mask = _segment_points_sam2(image, pts, lbls, sam2_id)
        else:
            raise ValueError("Select Object needs a click or object name.")

        Image.fromarray(mask, mode="L").save(output_mask_path, format="PNG")
        return output_mask_path
