"""Subprocess bridge from Lluna's worker to the official SeedVR2 scripts."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Callable

from backend.tools.installers import seedvr2 as seedvr_models


class SeedVRCancelled(RuntimeError):
    pass


def _dimensions(path: Path, target_long_edge: int) -> tuple[int, int]:
    if path.suffix.lower() in {".mp4", ".mov", ".mkv", ".avi", ".webm"}:
        import cv2

        capture = cv2.VideoCapture(str(path))
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        capture.release()
    else:
        from PIL import Image

        with Image.open(path) as image:
            width, height = image.size
    if width <= 0 or height <= 0:
        raise RuntimeError("SeedVR2 could not read the input dimensions.")
    long_edge = max(width, height)
    scale = max(1.0, float(target_long_edge) / float(long_edge))
    output_width = max(16, int(round(width * scale / 16.0)) * 16)
    output_height = max(16, int(round(height * scale / 16.0)) * 16)
    return output_height, output_width


def run_seedvr(
    payload: dict,
    *,
    cancel_event: threading.Event,
    progress: Callable[[int], None],
    log: Callable[[str], None],
) -> str:
    model_id = str(payload.get("model_id") or "seedvr2-3b")
    input_path = Path(str(payload.get("input_path") or "")).expanduser().resolve()
    output_raw = str(payload.get("output_path") or "").strip()
    output_path = Path(output_raw).expanduser().resolve() if output_raw else None
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    if output_path is None:
        raise RuntimeError("SeedVR2 output path is missing.")
    if not seedvr_models.cuda_compatible():
        raise RuntimeError("SeedVR2 inference requires an NVIDIA CUDA GPU.")
    if not seedvr_models.is_model_installed(model_id):
        raise RuntimeError(f"SeedVR2 {model_id} is not fully installed and configured.")

    script = seedvr_models.source_dir() / "projects" / (
        "inference_seedvr2_7b.py" if model_id.endswith("7b") else "inference_seedvr2_3b.py"
    )
    torchrun = seedvr_models.runtime_dir() / ("Scripts/torchrun.exe" if os.name == "nt" else "bin/torchrun")
    if not script.is_file() or not torchrun.is_file():
        raise RuntimeError("SeedVR2 source or isolated runtime is incomplete.")

    target_long_edge = max(512, int(payload.get("target_long_edge") or 2048))
    res_h, res_w = _dimensions(input_path, target_long_edge)
    sp_size = max(1, int(payload.get("sp_size") or 1))
    if input_path.suffix.lower() not in {".mp4", ".mov", ".mkv", ".avi", ".webm"}:
        sp_size = 1
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lluna-seedvr-job-") as raw:
        workspace = Path(raw)
        input_dir = workspace / "input"
        output_dir = workspace / "output"
        input_dir.mkdir()
        output_dir.mkdir()
        staged_name = input_path.name
        if input_path.suffix.lower() not in {".mp4", ".mov", ".mkv", ".avi", ".webm"}:
            staged_name = f"{input_path.stem}.png"
        staged_input = input_dir / staged_name
        shutil.copy2(input_path, staged_input)
        command = [
            str(torchrun),
            "--nproc-per-node",
            str(sp_size),
            str(script),
            "--video_path",
            str(input_dir),
            "--output_dir",
            str(output_dir),
            "--seed",
            str(int(payload.get("seed", 666))),
            "--res_h",
            str(res_h),
            "--res_w",
            str(res_w),
            "--sp_size",
            str(sp_size),
            "--checkpoint_dir",
            str(seedvr_models.checkpoints_dir()),
        ]
        if payload.get("out_fps"):
            command.extend(("--out_fps", str(float(payload["out_fps"]))))
        log(f"SeedVR2 {model_id}: {res_w}×{res_h}, sequence parallel {sp_size}")
        progress(5)
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(
            item for item in (str(seedvr_models.source_dir()), env.get("PYTHONPATH", "")) if item
        )
        with tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8") as output_log:
            process = subprocess.Popen(  # noqa: S603 - managed runtime and fixed script
                command,
                cwd=str(seedvr_models.source_dir()),
                env=env,
                stdout=output_log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            while process.poll() is None:
                if cancel_event.wait(0.5):
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    raise SeedVRCancelled("__cancelled__")
                progress(50)
            output_log.seek(0)
            output = output_log.read()
            if process.returncode:
                raise RuntimeError(output.strip()[-4000:] or "SeedVR2 inference failed.")
        generated = output_dir / staged_name
        if not generated.is_file():
            candidates = tuple(item for item in output_dir.iterdir() if item.is_file())
            if len(candidates) == 1:
                generated = candidates[0]
        if not generated.is_file():
            raise RuntimeError("SeedVR2 completed without producing an output file.")
        shutil.copy2(generated, output_path)
    progress(100)
    return str(output_path)
