"""Subprocess bridge from Midgard's inference worker to isolated SUPIR."""

from __future__ import annotations

import json
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Callable

from backend.tools import supir_models


class SupirCancelled(RuntimeError):
    pass


def run_supir(
    payload: dict,
    *,
    cancel_event: threading.Event,
    progress: Callable[[int], None],
    log: Callable[[str], None],
) -> str:
    if not supir_models.cuda_compatible():
        raise RuntimeError(
            "SUPIR inference requires an NVIDIA CUDA GPU. The installed model files were kept."
        )
    if not supir_models.is_model_installed():
        raise RuntimeError("SUPIR is not fully installed and configured.")
    if payload.get("variant") == "F" and not supir_models.checkpoint_path("F").is_file():
        raise RuntimeError("Import the official SUPIR-v0F checkpoint before selecting v0-F.")
    request = {
        **payload,
        "source_dir": str(supir_models.source_dir()),
        "q_checkpoint": str(supir_models.checkpoint_path("Q")),
        "f_checkpoint": (
            str(supir_models.checkpoint_path("F"))
            if supir_models.checkpoint_path("F").is_file()
            else ""
        ),
        "sdxl_checkpoint": str(supir_models.checkpoint_path("sdxl")),
        "llava_model_path": str(supir_models.dependency_dir("llava-v1.5-13b")),
        "llava_clip_path": str(supir_models.dependency_dir("clip-vit-large-patch14-336")),
        "sdxl_clip1_path": str(supir_models.dependency_dir("clip-vit-large-patch14")),
        "sdxl_clip2_path": str(
            supir_models.dependency_dir("clip-bigG") / "open_clip_pytorch_model.bin"
        ),
    }
    runner = Path(__file__).with_name("supir_runner.py")
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", encoding="utf-8", delete=False
    ) as handle:
        json.dump(request, handle)
        request_path = Path(handle.name)
    progress(5)
    log("Starting isolated SUPIR runtime…")
    with tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8") as output_log:
        process = subprocess.Popen(  # noqa: S603 - executable and runner are managed paths
            [str(supir_models.runtime_python()), str(runner), "--request", str(request_path)],
            stdout=output_log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            while process.poll() is None:
                if cancel_event.wait(0.2):
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    raise SupirCancelled("__cancelled__")
            output_log.seek(0)
            output = output_log.read()
            if process.returncode:
                raise RuntimeError(output.strip()[-4000:] or "SUPIR inference failed.")
            progress(100)
            return str(payload["output_path"])
        finally:
            request_path.unlink(missing_ok=True)
