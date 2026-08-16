"""SAM 3.1 (Object Multiplex) checkpoint and isolated-runtime lifecycle.

Replaces the old SAM2 + Grounding DINO "Select Object" stack. SAM 3.1's own
package (`sam3` on PyPI, https://github.com/facebookresearch/sam3) pins
`numpy>=1.26,<2`, which conflicts outright with Lluna's shared venv
(`numpy==2.3.5` in constraints.txt) - it cannot share site-packages with the
rest of the app, so it follows the same isolated-venv-plus-subprocess pattern
as SUPIR (backend/tools/installers/supir.py), not the shared worker process.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from backend.core.paths import PATHS
from backend.tools.installers._shared import bootstrap_reviewed_python, create_isolated_venv

# The pinned torch build the upstream README recommends (cu128 index). Isolated
# runtimes in this codebase hardcode one tested combination rather than
# dynamically picking a CUDA tag (see SUPIR/SeedVR2) - a cu128 wheel still runs
# fine on CPU-only machines, so this doesn't block the CPU fallback path.
SAM3_TORCH_INDEX_URL = "https://download.pytorch.org/whl/cu128"
SAM3_PACKAGES = (
    "torch==2.10.0",
    "torchvision",
)
SAM3_PACKAGE_VERSION = "0.1.4"
SAM3_HF_REPO = "facebook/sam3.1"
# The gated repo hosts checkpoints only ("no Hugging Face Transformers
# integration") - exact filenames aren't discoverable without an accepted
# access grant, so this downloads whatever the repo actually contains rather
# than a hardcoded per-file allowlist. snapshot_download_with_progress still
# verifies every downloaded file's size against what the Hub reports.
SAM3_ALLOW_PATTERNS = ("*.pt", "*.pth", "*.safetensors", "*.json", "*.yaml")


def sam3_root() -> Path:
    return PATHS.models_dir / "sam3"


def checkpoint_dir() -> Path:
    return sam3_root() / "checkpoints"


def runtime_dir() -> Path:
    return PATHS.data_dir / "model-runtimes" / "sam3-python"


def runtime_python() -> Path:
    return runtime_dir() / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _has_checkpoint_file() -> bool:
    """A real weight file, not just any entry - `Path.glob("*")` matches
    dotfiles/dot-dirs in Python (unlike a shell glob), so a stray `.cache`
    left by a failed/partial huggingface_hub download must not count as
    "installed". Mirrors the patterns `_find_checkpoint()` in
    backend/ai/runtimes/sam3.py actually looks for.
    """
    directory = checkpoint_dir()
    if not directory.is_dir():
        return False
    return any(directory.glob("**/*.pt")) or any(directory.glob("**/*.pth"))


def readiness() -> dict:
    return {
        "checkpoint": _has_checkpoint_file(),
        "runtime": runtime_python().is_file() and (runtime_dir() / "runtime.json").is_file(),
    }


def is_model_installed() -> bool:
    status = readiness()
    return status["checkpoint"] and status["runtime"]


def device_for_run() -> str:
    """GPU-first, CPU fallback - mirrors the rest of Lluna's device selection
    (backend.hardware.policy.select_execution_policy) rather than SAM3's own
    torch.cuda.is_available() default, since the isolated venv's torch build
    may not agree with the main process about what's available."""
    from backend.hardware.detector import get_hardware_profile
    from backend.hardware.policy import select_execution_policy

    backend = select_execution_policy(get_hardware_profile()).backend
    return "cuda" if backend == "cuda" else "cpu"


def _bootstrap_python() -> str:
    return bootstrap_reviewed_python(
        env_var="LLUNA_SAM3_PYTHON",
        versions=("3.12", "3.11", "3.10"),
        error_message=(
            "SAM 3.1 requires Python 3.10-3.12, and one could not be found or downloaded. "
            "Install Python 3.12 or point LLUNA_SAM3_PYTHON at an existing one."
        ),
        provision=True,
    )


def _install_runtime() -> None:
    if readiness()["runtime"]:
        return
    python = _bootstrap_python()
    create_isolated_venv(
        python_executable=python,
        target_dir=runtime_dir(),
        staging_name=".sam3-python.staging",
        pip_install_steps=[
            [*SAM3_PACKAGES, "--index-url", SAM3_TORCH_INDEX_URL],
            [f"sam3=={SAM3_PACKAGE_VERSION}"],
        ],
        runtime_metadata={
            "profile": "sam3-python",
            "packageVersion": SAM3_PACKAGE_VERSION,
            "packages": [*SAM3_PACKAGES, f"sam3=={SAM3_PACKAGE_VERSION}"],
            "managedBy": "lluna",
        },
    )


def download_checkpoint() -> Path:
    from backend.tools.shared.huggingface import (
        apply_hf_token_to_env,
        snapshot_download_with_progress,
    )

    destination = checkpoint_dir()
    if readiness()["checkpoint"]:
        return destination
    apply_hf_token_to_env()
    destination.mkdir(parents=True, exist_ok=True)
    try:
        snapshot_download_with_progress(
            repo_id=SAM3_HF_REPO,
            local_dir=str(destination),
            allow_patterns=list(SAM3_ALLOW_PATTERNS),
        )
    except Exception as e:
        msg = str(e)
        lower = msg.lower()
        if "401" in msg or "403" in msg or "gated" in lower or "unauthorized" in lower or "restricted" in lower:
            raise RuntimeError(
                f"{msg}\n\n"
                f"{SAM3_HF_REPO} is a gated repo. Visit https://huggingface.co/{SAM3_HF_REPO}, "
                "sign in, and request/accept access - Meta reviews these requests, so approval "
                "isn't instant. Then connect a Hugging Face read token in Settings -> Models "
                "(the Hugging Face connection section) and retry the install."
            ) from e
        raise
    if not readiness()["checkpoint"]:
        raise RuntimeError(
            f"Hugging Face did not provide any checkpoint files from {SAM3_HF_REPO}. "
            "Make sure you've been granted access to the gated repo and are signed in."
        )
    return destination


KIND_SAM3 = "sam3"


def discard_partial(key: str = "sam3") -> None:
    del key
    status = readiness()
    if not status["checkpoint"]:
        shutil.rmtree(checkpoint_dir(), ignore_errors=True)
    runtime_staging = runtime_dir().with_name(".sam3-python.staging")
    shutil.rmtree(runtime_staging, ignore_errors=True)
    if not status["runtime"]:
        shutil.rmtree(runtime_dir(), ignore_errors=True)


def install_model() -> None:
    from backend.tools.shared.download_registry import (
        DownloadCancelled,
        ModelDownloadRegistry,
    )

    reg = ModelDownloadRegistry.instance()
    reg.begin(KIND_SAM3, "sam3")
    try:
        reg.check_cancelled()
        download_checkpoint()
        reg.check_cancelled()
        if not readiness()["runtime"]:
            _bootstrap_python()
        _install_runtime()
        reg.check_cancelled()
    except DownloadCancelled:
        discard_partial()
        reg.fail(KIND_SAM3, "sam3", keep_pending=True)
        raise
    except Exception:
        discard_partial()
        reg.fail(KIND_SAM3, "sam3", keep_pending=False)
        raise
    reg.complete(KIND_SAM3, "sam3")


def uninstall_model() -> None:
    if sam3_root().exists():
        shutil.rmtree(sam3_root())
    if runtime_dir().exists():
        shutil.rmtree(runtime_dir())
