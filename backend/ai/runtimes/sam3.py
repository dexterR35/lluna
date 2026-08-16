"""Subprocess bridge from Lluna's inference worker to isolated SAM 3.1."""

from __future__ import annotations

import json
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Callable

from backend.tools.installers import sam3 as sam3_models
from backend.tools.shared.process import ProcessManager


class Sam3Cancelled(RuntimeError):
    pass


def _find_checkpoint() -> Path:
    directory = sam3_models.checkpoint_dir()
    candidates = sorted({*directory.glob("**/*.pt"), *directory.glob("**/*.pth")})
    if not candidates:
        raise RuntimeError("No SAM 3.1 checkpoint file was found after download.")
    if len(candidates) > 1:
        # Prefer a file that looks like the main model weights over any
        # auxiliary/optimizer checkpoint the repo might also ship.
        preferred = [item for item in candidates if "sam3" in item.name.lower()]
        if len(preferred) == 1:
            return preferred[0]
    return candidates[0]


def run_select_object(
    image_path: str,
    output_mask_path: str,
    *,
    points: list | None = None,
    labels: list | None = None,
    text: str | None = None,
    confidence_threshold: float | None = None,
    mask_threshold: float | None = None,
    cancel_event: threading.Event | None = None,
    progress: Callable[[int], None] | None = None,
) -> str:
    if not sam3_models.is_model_installed():
        raise RuntimeError("SAM 3.1 is not fully installed.")
    request = {
        "checkpoint_path": str(_find_checkpoint()),
        "input_path": image_path,
        "output_mask_path": output_mask_path,
        "text": text or "",
        "points": points or [],
        "labels": labels or [],
        "confidence_threshold": confidence_threshold,
        "mask_threshold": mask_threshold,
        "device": sam3_models.device_for_run(),
    }
    runner = Path(__file__).with_name("sam3_process.py")
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", encoding="utf-8", delete=False
    ) as handle:
        json.dump(request, handle)
        request_path = Path(handle.name)
    if progress:
        progress(5)
    with tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8") as output_log:
        process = subprocess.Popen(  # noqa: S603 - executable and runner are managed paths
            [str(sam3_models.runtime_python()), str(runner), "--request", str(request_path)],
            stdout=output_log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        # Route cancellation through ProcessManager, which also reaps the process's descendants.
        ProcessManager.instance().add_process(process, name="sam3-worker")
        try:
            while process.poll() is None:
                if cancel_event is not None and cancel_event.wait(0.2):
                    ProcessManager.instance().terminate_by_process(process, quiet=True)
                    raise Sam3Cancelled("__cancelled__")
            output_log.seek(0)
            output = output_log.read()
            if process.returncode:
                raise RuntimeError(output.strip()[-4000:] or "SAM 3.1 inference failed.")
            if progress:
                progress(100)
            return output_mask_path
        finally:
            ProcessManager.instance().remove_process("sam3-worker")
            request_path.unlink(missing_ok=True)
