"""Subprocess bridge from Lluna's worker to the official SeedVR2 scripts."""

from __future__ import annotations

import os
import random
import shutil
import socket
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Callable

from backend.hardware.gpu import detect_torch_cuda_gpus
from backend.tools.installers import seedvr2 as seedvr_models
from backend.tools.shared.process import ProcessManager


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


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


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
    # When torch.distributed.run is used below (sp_size > 1) it's invoked as
    # `python -m torch.distributed.run` rather than the compiled torchrun.exe
    # launcher: on Windows that launcher stub swallows stdout/stderr when the
    # interpreter crashes before argparse runs (e.g. a missing runtime DLL during
    # `import torch`), leaving run_seedvr()'s captured output empty and only
    # "SeedVR2 inference failed." to show the user. `python -m` reliably
    # propagates the real traceback through the redirected pipe instead.
    runtime_python = seedvr_models.runtime_python()
    if not script.is_file() or not runtime_python.is_file():
        raise RuntimeError("SeedVR2 source or isolated runtime is incomplete.")

    target_long_edge = max(512, int(payload.get("target_long_edge") or 2048))
    res_h, res_w = _dimensions(input_path, target_long_edge)
    sp_size = max(1, int(payload.get("sp_size") or 1))
    if input_path.suffix.lower() not in {".mp4", ".mov", ".mkv", ".avi", ".webm"}:
        sp_size = 1
    else:
        gpu_count = len(detect_torch_cuda_gpus())
        if gpu_count:
            sp_size = min(sp_size, gpu_count)
    seed_value = int(payload.get("seed", 666))
    if seed_value < 0:
        seed_value = random.randint(0, 2_147_483_647)
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
        script_args = [
            "--video_path",
            str(input_dir),
            "--output_dir",
            str(output_dir),
            "--seed",
            str(seed_value),
            "--res_h",
            str(res_h),
            "--res_w",
            str(res_w),
            "--sp_size",
            str(sp_size),
            "--checkpoint_dir",
            str(seedvr_models.checkpoints_dir()),
        ]
        # torch's Windows wheels aren't built with libuv, and torchrun's own
        # elastic-agent rendezvous hardcodes socket.getfqdn() for the address it
        # hands to worker processes with no override -- which hangs forever on a
        # machine whose hostname doesn't resolve on its local network (common on
        # corporate/VPN setups). For the common single-process case, skip torchrun
        # entirely: dist.init_process_group()'s own env:// path reads MASTER_ADDR
        # straight from the environment with no fqdn substitution, so setting the
        # same env vars torchrun would have gets there without the broken lookup.
        libuv_env = {"USE_LIBUV": "0"}
        if sp_size == 1:
            command = [str(runtime_python), str(script), *script_args]
            libuv_env.update(
                MASTER_ADDR="127.0.0.1",
                MASTER_PORT=str(_free_port()),
                RANK="0",
                WORLD_SIZE="1",
                LOCAL_RANK="0",
            )
        else:
            command = [
                str(runtime_python),
                "-m",
                "torch.distributed.run",
                "--standalone",
                "--nproc-per-node",
                str(sp_size),
                str(script),
                *script_args,
            ]
        if not model_id.endswith("7b"):
            # The 3B script accepts an explicit checkpoint filename so GGUF
            # variants (which share checkpoints_dir() with the fp16/bf16 model)
            # load the right file; the 7B script has no GGUF variants yet.
            command.extend(
                ("--checkpoint_filename", seedvr_models.MODEL_CONFIG[model_id]["checkpoint"])
            )
        if payload.get("out_fps"):
            command.extend(("--out_fps", str(float(payload["out_fps"]))))
        log(f"SeedVR2 {model_id}: {res_w}×{res_h}, sequence parallel {sp_size}")
        progress(5)
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(
            item for item in (str(seedvr_models.source_dir()), env.get("PYTHONPATH", "")) if item
        )
        env.update(libuv_env)
        with tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8") as output_log:
            process = subprocess.Popen(  # noqa: S603 - managed runtime and fixed script
                command,
                cwd=str(seedvr_models.source_dir()),
                env=env,
                stdout=output_log,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=os.name != "nt",
            )
            # When sp_size > 1, torchrun spawns --nproc-per-node worker children;
            # terminating only the launcher PID can orphan them, so cancellation
            # goes through ProcessManager, which also reaps the process's
            # descendants (a no-op tree of one for the sp_size == 1 direct case).
            ProcessManager.instance().add_process(process, name="seedvr2-worker")
            try:
                while process.poll() is None:
                    if cancel_event.wait(0.5):
                        ProcessManager.instance().terminate_by_process(process, quiet=True)
                        raise SeedVRCancelled("__cancelled__")
                    progress(50)
            finally:
                ProcessManager.instance().remove_process("seedvr2-worker")
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
