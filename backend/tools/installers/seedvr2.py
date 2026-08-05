"""Bundled SeedVR2 inference and isolated-runtime lifecycle.

The reviewed SeedVR2 inference source is shipped in ``backend/ai/seedvr2``.
Installation downloads only the optional Hugging Face weights and creates the
isolated CUDA runtime required by the upstream implementation.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from backend.core.atomic import atomic_write_json
from backend.core.paths import PATHS

KIND_SEEDVR = "seedvr2"
SEEDVR_COMMIT = "e4de8c24441a67e1b7df56abea10645059bb1185"
SEEDVR_SOURCE_REPO = "ByteDance-Seed/SeedVR"
SEEDVR_RUNTIME_PROFILE = "seedvr-python"

MODEL_CONFIG = {
    "seedvr2-3b": {
        "repo": "ByteDance-Seed/SeedVR2-3B",
        "checkpoint": "seedvr2_ema_3b.pth",
        "minimum_vram_mb": 24576,
    },
    "seedvr2-7b": {
        "repo": "ByteDance-Seed/SeedVR2-7B",
        "checkpoint": "seedvr2_ema_7b.pth",
        "minimum_vram_mb": 49152,
    },
}

SEEDVR_PACKAGES = (
    "einops==0.7.0",
    "torch==2.4.0",
    "torchvision==0.19.0",
    "omegaconf==2.3.0",
    "opencv-python==4.9.0.80",
    "diffusers==0.33.1",
    "rotary-embedding-torch==0.5.3",
    "transformers==4.46.2",
    "mediapy==1.2.0",
    "accelerate==0.33.0",
    "numpy==1.24.4",
    "pillow==10.3.0",
    "scipy==1.13.1",
    "safetensors==0.4.3",
    "pyyaml==6.0.1",
    "av==12.0.0",
    "timm==1.0.11",
    "tqdm",
    "ninja",
)


def models_root() -> Path:
    root = PATHS.models_dir / "seedvr2"
    root.mkdir(parents=True, exist_ok=True)
    return root


def source_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "ai" / "seedvr2"


def checkpoints_dir() -> Path:
    return models_root() / "ckpts"


def model_dir(model_id: str) -> Path:
    if model_id not in MODEL_CONFIG:
        raise ValueError(f"Unknown SeedVR2 model: {model_id}")
    return models_root() / model_id


def runtime_dir() -> Path:
    return PATHS.data_dir / "model-runtimes" / SEEDVR_RUNTIME_PROFILE


def runtime_python() -> Path:
    return runtime_dir() / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _source_ready() -> bool:
    return all(
        (
            (source_dir() / "projects" / "inference_seedvr2_3b.py").is_file(),
            (source_dir() / "projects" / "inference_seedvr2_7b.py").is_file(),
            (source_dir() / "configs_3b" / "main.yaml").is_file(),
            (source_dir() / "configs_7b" / "main.yaml").is_file(),
            (source_dir() / "pos_emb.pt").is_file(),
            (source_dir() / "neg_emb.pt").is_file(),
        )
    )


def readiness(model_id: str) -> dict[str, bool]:
    config = MODEL_CONFIG[model_id]
    return {
        "source": _source_ready(),
        "runtime": runtime_python().is_file() and (runtime_dir() / "runtime.json").is_file(),
        "checkpoint": (checkpoints_dir() / config["checkpoint"]).is_file(),
        "vae": (checkpoints_dir() / "ema_vae.pth").is_file(),
        "model": (model_dir(model_id) / ".lluna-installed").is_file(),
    }


def is_model_installed(model_id: str) -> bool:
    status = readiness(model_id)
    return all(status.values())


def cuda_compatible() -> bool:
    from backend.hardware.detector import get_hardware_profile
    from backend.hardware.policy import select_execution_policy

    return select_execution_policy(get_hardware_profile()).backend == "cuda"


def _bootstrap_python() -> str:
    configured = os.environ.get("LLUNA_SEEDVR_PYTHON", "").strip()
    candidates: list[str | Path] = [configured] if configured else []
    candidates.extend(("python3.10", "python3.9"))
    checked: set[str] = set()
    for candidate in candidates:
        executable = str(candidate) if Path(candidate).is_file() else shutil.which(str(candidate))
        if not executable:
            continue
        executable = str(Path(executable).resolve())
        if executable in checked:
            continue
        checked.add(executable)
        result = subprocess.run(  # noqa: S603 - executable is selected from a reviewed Python version
            [executable, "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip() in {"3.10", "3.9"}:
            return executable
    raise RuntimeError(
        "SeedVR2 requires Python 3.10 or 3.9. Install Python 3.10 or set LLUNA_SEEDVR_PYTHON."
    )


def _install_runtime() -> None:
    if runtime_python().is_file() and (runtime_dir() / "runtime.json").is_file():
        return
    if os.name != "posix":
        raise RuntimeError("The official SeedVR2 runtime currently supports Linux CUDA installations only.")
    python = _bootstrap_python()
    target = runtime_dir()
    staging = target.with_name(".seedvr-python.staging")
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    staging.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(  # noqa: S603 - reviewed Python executable and managed venv path
        [python, "-m", "venv", str(staging)], check=True, timeout=300
    )
    runtime = staging / "bin" / "python"
    subprocess.run(  # noqa: S603 - managed venv and reviewed CUDA package pins
        [
            str(runtime),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "torch==2.4.0",
            "torchvision==0.19.0",
            "--index-url",
            "https://download.pytorch.org/whl/cu121",
        ],
        check=True,
        timeout=3600,
    )
    subprocess.run(  # noqa: S603 - managed venv and reviewed package pins
        [str(runtime), "-m", "pip", "install", "--disable-pip-version-check", *SEEDVR_PACKAGES],
        check=True,
        timeout=3600,
    )
    subprocess.run(  # noqa: S603 - managed venv and fixed package name
        [
            str(runtime),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "flash_attn==2.5.9.post1",
            "--no-build-isolation",
        ],
        check=True,
        timeout=1800,
    )
    version_probe = subprocess.run(  # noqa: S603 - managed venv and fixed probe
        [str(runtime), "-c", "import sys; print(f'cp{sys.version_info.major}{sys.version_info.minor}')"],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    python_tag = version_probe.stdout.strip()
    wheel = next(checkpoints_dir().glob(f"apex-0.1-{python_tag}-*.whl"), None)
    if wheel is not None:
        subprocess.run(  # noqa: S603 - managed venv and downloaded official wheel
            [str(runtime), "-m", "pip", "install", str(wheel)], check=True, timeout=900
        )
    else:
        raise RuntimeError("SeedVR2 could not find the official prebuilt Apex wheel for Python 3.10.")
    atomic_write_json(
        staging / "runtime.json",
        {
            "profile": SEEDVR_RUNTIME_PROFILE,
            "bundledSource": SEEDVR_SOURCE_REPO,
            "sourceCommit": SEEDVR_COMMIT,
            "packages": list(SEEDVR_PACKAGES),
            "managedBy": "lluna",
        },
    )
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    staging.replace(target)


def _download_checkpoint(model_id: str) -> None:
    from backend.tools.shared.huggingface import snapshot_download_with_progress

    config = MODEL_CONFIG[model_id]
    staging = models_root() / ".downloads" / model_id
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    patterns = [config["checkpoint"], "ema_vae.pth", "apex-*.whl"]
    snapshot_download_with_progress(
        repo_id=config["repo"],
        local_dir=str(staging),
        allow_patterns=patterns,
    )
    required = (staging / config["checkpoint"], staging / "ema_vae.pth")
    if not all(path.is_file() for path in required):
        raise RuntimeError(f"Hugging Face did not provide the complete SeedVR2 {model_id} checkpoint.")
    checkpoints_dir().mkdir(parents=True, exist_ok=True)
    for filename in (config["checkpoint"], "ema_vae.pth"):
        source = staging / filename
        target = checkpoints_dir() / filename
        temporary = target.with_suffix(target.suffix + ".part")
        source.replace(temporary)
        temporary.replace(target)
    for wheel in staging.glob("apex-*.whl"):
        shutil.copy2(wheel, checkpoints_dir() / wheel.name)
    if not any(checkpoints_dir().glob("apex-*.whl")):
        apex_staging = models_root() / ".downloads" / "apex"
        shutil.rmtree(apex_staging, ignore_errors=True)
        snapshot_download_with_progress(
            repo_id="ByteDance-Seed/SeedVR2-3B",
            local_dir=str(apex_staging),
            allow_patterns=["apex-*.whl"],
        )
        for wheel in apex_staging.glob("apex-*.whl"):
            shutil.copy2(wheel, checkpoints_dir() / wheel.name)
        shutil.rmtree(apex_staging, ignore_errors=True)
    shutil.rmtree(staging, ignore_errors=True)


def install_model(model_id: str) -> Path:
    """Install one official SeedVR2 variant and its shared runtime assets."""
    if model_id not in MODEL_CONFIG:
        raise ValueError(f"Unknown SeedVR2 model: {model_id}")
    if not cuda_compatible():
        raise RuntimeError("SeedVR2 requires an NVIDIA CUDA GPU. Model files were not installed.")
    from backend.tools.shared.download_registry import DownloadCancelled, ModelDownloadRegistry

    registry = ModelDownloadRegistry.instance()
    registry.begin(KIND_SEEDVR, model_id)
    try:
        registry.check_cancelled()
        _download_checkpoint(model_id)
        registry.check_cancelled()
        _install_runtime()
        marker = model_dir(model_id) / ".lluna-installed"
        marker.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(
            marker,
            {"modelId": model_id, "repo": MODEL_CONFIG[model_id]["repo"], "managedBy": "lluna"},
        )
        registry.complete(KIND_SEEDVR, model_id)
        return model_dir(model_id)
    except DownloadCancelled:
        discard_partial(model_id)
        registry.fail(KIND_SEEDVR, model_id, keep_pending=True)
        raise
    except Exception:
        discard_partial(model_id)
        registry.fail(KIND_SEEDVR, model_id, keep_pending=False)
        raise


def discard_partial(model_id: str) -> None:
    staging = models_root() / ".downloads" / model_id
    shutil.rmtree(staging, ignore_errors=True)


def uninstall_model(model_id: str) -> None:
    if model_id not in MODEL_CONFIG:
        raise ValueError(f"Unknown SeedVR2 model: {model_id}")
    config = MODEL_CONFIG[model_id]
    discard_partial(model_id)
    for filename in (config["checkpoint"],):
        (checkpoints_dir() / filename).unlink(missing_ok=True)
    if not any((model_dir(item) / ".lluna-installed").is_file() for item in MODEL_CONFIG):
        shutil.rmtree(checkpoints_dir(), ignore_errors=True)
        shutil.rmtree(runtime_dir(), ignore_errors=True)
