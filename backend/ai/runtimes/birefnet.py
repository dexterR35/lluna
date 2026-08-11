"""Subprocess bridge from Lluna's inference worker to isolated BiRefNet.

BiRefNet's official HF snapshots ship custom modeling code that is loaded
with ``trust_remote_code=True`` (see birefnet_process.py). That code now runs
inside its own pinned, isolated venv (backend/tools/installers/birefnet.py),
the same pattern already used for SUPIR and SeedVR2, instead of importing
directly into the main app's process and dependency environment.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from backend.tools.installers import birefnet as birefnet_models
from backend.tools.shared.process import ProcessManager


class BiRefNetCancelled(RuntimeError):
    pass


def _resolve_model_root(model_id: str, model_path: str | None) -> Path:
    if model_path:
        root = Path(model_path)
        if not birefnet_models.is_model_installed_at(root):
            raise RuntimeError(f"BiRefNet model at '{model_path}' is missing config.json or weights.")
        return root
    if not birefnet_models.is_model_installed(model_id):
        raise RuntimeError(f"BiRefNet model '{model_id}' is not installed. Install it in Settings → Models.")
    return birefnet_models.model_dir(model_id)


def _run(request: dict, *, cancel_event=None, progress: Callable[[int], None] | None = None) -> None:
    if not birefnet_models.runtime_python().is_file():
        raise RuntimeError("The isolated BiRefNet runtime is not installed. Install it in Settings → Models.")
    runner = Path(__file__).with_name("birefnet_process.py")
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", encoding="utf-8", delete=False
    ) as handle:
        json.dump(request, handle)
        request_path = Path(handle.name)
    if progress:
        progress(5)
    with tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8") as output_log:
        process = subprocess.Popen(  # noqa: S603 - executable and runner are managed paths
            [str(birefnet_models.runtime_python()), str(runner), "--request", str(request_path)],
            stdout=output_log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        ProcessManager.instance().add_process(process, name="birefnet-worker")
        try:
            while process.poll() is None:
                if cancel_event is not None and cancel_event.wait(0.2):
                    ProcessManager.instance().terminate_by_process(process, quiet=True)
                    raise BiRefNetCancelled("__cancelled__")
                if progress:
                    progress(50)
            output_log.seek(0)
            output = output_log.read()
            if process.returncode:
                raise RuntimeError(output.strip()[-4000:] or "BiRefNet inference failed.")
        finally:
            ProcessManager.instance().remove_process("birefnet-worker")
            request_path.unlink(missing_ok=True)
    if progress:
        progress(100)


def release_models() -> None:
    # Each job now runs in its own subprocess (isolated venv), which exits
    # and releases all VRAM/RAM on completion - there is no persistent
    # in-process cache left to release here.
    pass


def process_image(
    input_path: str,
    output_path: str,
    *,
    model_id: str,
    resolution: int = 1024,
    threshold: float = 0.5,
    feather: int = 0,
    output_mode: str = "transparent",
    background_color: str = "#ffffff",
    model_path: str | None = None,
    precision: str = "auto",
    mask_output_path: str | None = None,
    alpha_output_path: str | None = None,
    hardware_acceleration: bool = True,
) -> None:
    root = _resolve_model_root(model_id, model_path)
    request = {
        "job": "image",
        "model_root": str(root),
        "input_path": input_path,
        "output_path": output_path,
        "resolution": int(resolution),
        "threshold": float(threshold),
        "feather": int(feather),
        "output_mode": output_mode,
        "background_color": background_color,
        "precision": precision,
        "mask_output_path": mask_output_path,
        "alpha_output_path": alpha_output_path,
        "hardware_acceleration": bool(hardware_acceleration),
    }
    _run(request)


def process_video(
    input_path: str,
    output_path: str,
    *,
    model_id: str,
    resolution: int = 1024,
    threshold: float = 0.5,
    feather: int = 0,
    output_mode: str = "transparent",
    background_color: str = "#ffffff",
    model_path: str | None = None,
    precision: str = "auto",
    progress: Callable[[int], None] | None = None,
    cancel_event=None,
    hardware_acceleration: bool = True,
) -> None:
    from backend.tools.media.ffmpeg import FFmpegCLI

    root = _resolve_model_root(model_id, model_path)
    request = {
        "job": "video",
        "model_root": str(root),
        "input_path": input_path,
        "output_path": output_path,
        "resolution": int(resolution),
        "threshold": float(threshold),
        "feather": int(feather),
        "output_mode": output_mode,
        "background_color": background_color,
        "precision": precision,
        "ffmpeg_path": FFmpegCLI.instance().ffmpeg_path,
        "hardware_acceleration": bool(hardware_acceleration),
    }
    _run(request, cancel_event=cancel_event, progress=progress)
