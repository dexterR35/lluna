"""Merge two videos into one comparison reel (side-by-side or stacked)."""

from __future__ import annotations

import cv2
import numpy as np


def _scale_to_height(frame: np.ndarray, target_h: int) -> np.ndarray:
    h, w = frame.shape[:2]
    if h == target_h:
        return frame
    new_w = max(1, int(round(w * (target_h / float(h)))))
    return cv2.resize(frame, (new_w, target_h), interpolation=cv2.INTER_AREA)


def _scale_to_width(frame: np.ndarray, target_w: int) -> np.ndarray:
    h, w = frame.shape[:2]
    if w == target_w:
        return frame
    new_h = max(1, int(round(h * (target_w / float(w)))))
    return cv2.resize(frame, (target_w, new_h), interpolation=cv2.INTER_AREA)


def merge_video(
    video_input_path0: str,
    video_input_path1: str,
    video_output_path: str,
    *,
    layout: str = "horizontal",
) -> str:
    """
    Merge two videos into a comparison file.

    layout:
      - ``horizontal`` — left = path0 (original), right = path1 (cleaned)
      - ``vertical`` — top = path0, bottom = path1
    """
    if layout not in ("horizontal", "vertical"):
        raise ValueError(f"Unsupported layout: {layout}")

    cap0 = cv2.VideoCapture(video_input_path0)
    cap1 = cv2.VideoCapture(video_input_path1)
    if not cap0.isOpened():
        cap1.release()
        raise RuntimeError(f"Cannot open video: {video_input_path0}")
    if not cap1.isOpened():
        cap0.release()
        raise RuntimeError(f"Cannot open video: {video_input_path1}")

    try:
        fps0 = float(cap0.get(cv2.CAP_PROP_FPS) or 0) or 30.0
        fps1 = float(cap1.get(cv2.CAP_PROP_FPS) or 0) or 30.0
        fps = fps1 if fps1 > 0 else fps0

        w0 = int(cap0.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        h0 = int(cap0.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        w1 = int(cap1.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        h1 = int(cap1.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        if w0 <= 0 or h0 <= 0 or w1 <= 0 or h1 <= 0:
            raise RuntimeError("Invalid video dimensions")

        if layout == "horizontal":
            target_h = max(h0, h1)
            sample0 = _scale_to_height(np.zeros((h0, w0, 3), dtype=np.uint8), target_h)
            sample1 = _scale_to_height(np.zeros((h1, w1, 3), dtype=np.uint8), target_h)
            out_w = sample0.shape[1] + sample1.shape[1]
            out_h = target_h
        else:
            target_w = max(w0, w1)
            sample0 = _scale_to_width(np.zeros((h0, w0, 3), dtype=np.uint8), target_w)
            sample1 = _scale_to_width(np.zeros((h1, w1, 3), dtype=np.uint8), target_w)
            out_w = target_w
            out_h = sample0.shape[0] + sample1.shape[0]

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(video_output_path, fourcc, fps, (out_w, out_h))
        if not writer.isOpened():
            raise RuntimeError(f"Cannot write video: {video_output_path}")

        try:
            while True:
                ret0, frame0 = cap0.read()
                ret1, frame1 = cap1.read()
                if not ret0 or not ret1:
                    break
                if layout == "horizontal":
                    a = _scale_to_height(frame0, out_h)
                    b = _scale_to_height(frame1, out_h)
                    merged = cv2.hconcat([a, b])
                else:
                    a = _scale_to_width(frame0, out_w)
                    b = _scale_to_width(frame1, out_w)
                    merged = cv2.vconcat([a, b])
                if merged.shape[1] != out_w or merged.shape[0] != out_h:
                    merged = cv2.resize(merged, (out_w, out_h), interpolation=cv2.INTER_AREA)
                writer.write(merged)
        finally:
            writer.release()
    finally:
        cap0.release()
        cap1.release()

    return video_output_path


if __name__ == "__main__":
    v0_path = "../../test/test4.mp4"
    v1_path = "../../test/test4_no_sub(1).mp4"
    video_out_path = "../../test/demo.mp4"
    merge_video(v0_path, v1_path, video_out_path, layout="horizontal")
