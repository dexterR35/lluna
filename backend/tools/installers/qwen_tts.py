"""Qwen3-TTS (12Hz, 1.7B, CustomVoice) checkpoint and isolated-runtime lifecycle.

The upstream `qwen-tts` PyPI package pins `transformers==4.57.3`, which
conflicts outright with Lluna's shared venv (`transformers>=5.5.0` in
requirements.txt) - it cannot share site-packages with the rest of the app,
so it follows the same isolated-venv-plus-subprocess pattern as SAM 3.1
(backend/tools/installers/sam3.py) rather than the shared worker process.

Every checkpoint file below is pinned by exact size and SHA-256, computed
directly from https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice at
the time this installer was written (the two `.safetensors` hashes came from
the Hub's LFS metadata; the rest are small plain-git files hashed locally).
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from backend.core.paths import PATHS
from backend.tools.installers._shared import (
    bootstrap_reviewed_python,
    create_isolated_venv,
    verify_pinned_artifact,
)

KIND_QWEN_TTS = "qwen3_tts"
QWEN_TTS_REPO = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
QWEN_TTS_REVISION = "0c0e3051f131929182e2c023b9537f8b1c68adfe"
QWEN_TTS_PACKAGE_VERSION = "0.1.1"
QWEN_TTS_RUNTIME_PROFILE = "qwen3-tts-python"

# The 9 pre-defined CustomVoice speakers this checkpoint ships with (see the
# model card) - listed here once so the installer and the graph node draw
# from the same source of truth.
QWEN_TTS_SPEAKERS = (
    "Vivian",
    "Serena",
    "Uncle_Fu",
    "Dylan",
    "Eric",
    "Ryan",
    "Aiden",
    "Ono_Anna",
    "Sohee",
)
QWEN_TTS_LANGUAGES = (
    "Chinese",
    "English",
    "Japanese",
    "Korean",
    "German",
    "French",
    "Russian",
    "Portuguese",
    "Spanish",
    "Italian",
)

# relative_path -> (size_bytes, sha256)
QWEN_TTS_FILES: dict[str, tuple[int, str]] = {
    "config.json": (4908, "17a07f527a1c25ea30b4e023a184482a23d3e279d697b1dc81b1bde498d29cf9"),
    "generation_config.json": (245, "f1b90b4513f3b34c62851049e2492d7b4c5940daf1276f89c82b8ef04127f3aa"),
    "merges.txt": (1671839, "599bab54075088774b1733fde865d5bd747cbcc7a547c5bc12610e874e26f5e3"),
    "model.safetensors": (
        3833402552,
        "38b1d5971bdbd982b561cccec982669a53b0537c3cf5e9bd4778ed07bb2f5137",
    ),
    "preprocessor_config.json": (
        127,
        "efdde1022ea9d76928bf7a9cd53139138f5ba2e466e837f08f6105ab1af1c119",
    ),
    "speech_tokenizer/config.json": (
        2336,
        "ee65bb901c876664ab8707c487157aa1a6ee57c65969b28fb5ec9dc211e68167",
    ),
    "speech_tokenizer/configuration.json": (
        76,
        "6bc26d64eb5024b4d1dab5a52371958b429256d6c9d59787f1f5294a54e0cebd",
    ),
    "speech_tokenizer/model.safetensors": (
        682293092,
        "836b7b357f5ea43e889936a3709af68dfe3751881acefe4ecf0dbd30ba571258",
    ),
    "speech_tokenizer/preprocessor_config.json": (
        234,
        "fcb3805e597e786d4067706e602f6688524640f8d3396790e2e09b5942fcbdfb",
    ),
    "tokenizer_config.json": (7344, "dc3c31c3bdaedd5016382bb3cbe07323026775ad51f5a4fb564505992ae4a670"),
    "vocab.json": (2776833, "ca10d7e9fb3ed18575dd1e277a2579c16d108e32f27439684afa0e10b1440910"),
}

# qwen-tts's own requires_dist pins transformers/accelerate/etc but not torch
# itself, so torch+torchaudio are installed first from the CUDA wheel index.
# Left unpinned (unlike SAM3's torch==2.10.0) because there is no CUDA GPU
# available to validate one specific torch/torchaudio pair against qwen-tts
# 0.1.1 before shipping this - pip resolves whatever's current on the index.
QWEN_TTS_TORCH_INDEX_URL = "https://download.pytorch.org/whl/cu128"
QWEN_TTS_TORCH_PACKAGES = ("torch", "torchaudio")


def models_root() -> Path:
    root = PATHS.models_dir / "qwen3-tts" / "customvoice"
    root.mkdir(parents=True, exist_ok=True)
    return root


def runtime_dir() -> Path:
    return PATHS.data_dir / "model-runtimes" / QWEN_TTS_RUNTIME_PROFILE


def runtime_python() -> Path:
    return runtime_dir() / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _has_checkpoint_files() -> bool:
    root = models_root()
    return all((root / relative_path).is_file() for relative_path in QWEN_TTS_FILES)


def readiness() -> dict[str, bool]:
    return {
        "checkpoint": _has_checkpoint_files(),
        "runtime": runtime_python().is_file() and (runtime_dir() / "runtime.json").is_file(),
    }


def is_model_installed() -> bool:
    status = readiness()
    return status["checkpoint"] and status["runtime"]


def cuda_compatible() -> bool:
    from backend.hardware.detector import get_hardware_profile
    from backend.hardware.policy import select_execution_policy

    return select_execution_policy(get_hardware_profile()).backend == "cuda"


def _bootstrap_python() -> str:
    return bootstrap_reviewed_python(
        env_var="LLUNA_QWEN_TTS_PYTHON",
        versions=("3.12", "3.11", "3.10"),
        error_message=(
            "Qwen3-TTS requires Python 3.10-3.12, and one could not be found or downloaded. "
            "Install Python 3.12 or point LLUNA_QWEN_TTS_PYTHON at an existing one."
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
        staging_name=".qwen3-tts-python.staging",
        pip_install_steps=[
            [*QWEN_TTS_TORCH_PACKAGES, "--index-url", QWEN_TTS_TORCH_INDEX_URL],
            [f"qwen-tts=={QWEN_TTS_PACKAGE_VERSION}"],
        ],
        runtime_metadata={
            "profile": QWEN_TTS_RUNTIME_PROFILE,
            "packageVersion": QWEN_TTS_PACKAGE_VERSION,
            "packages": [*QWEN_TTS_TORCH_PACKAGES, f"qwen-tts=={QWEN_TTS_PACKAGE_VERSION}"],
            "managedBy": "lluna",
        },
    )


def _download_checkpoint() -> None:
    from backend.tools.shared.huggingface import snapshot_download_with_progress

    root = models_root()
    staging = root.parent / ".downloads" / "customvoice"
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    snapshot_download_with_progress(
        repo_id=QWEN_TTS_REPO,
        revision=QWEN_TTS_REVISION,
        local_dir=str(staging),
        allow_patterns=list(QWEN_TTS_FILES),
    )
    for relative_path, (expected_size, expected_sha256) in QWEN_TTS_FILES.items():
        downloaded = staging / relative_path
        if not downloaded.is_file():
            raise RuntimeError(f"Hugging Face did not provide {relative_path} from {QWEN_TTS_REPO}.")
        verify_pinned_artifact(
            downloaded, expected_size=expected_size, expected_sha256=expected_sha256
        )
    for relative_path in QWEN_TTS_FILES:
        source = staging / relative_path
        target = root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".part")
        source.replace(temporary)
        temporary.replace(target)
    shutil.rmtree(staging, ignore_errors=True)


def discard_partial(key: str = "customvoice") -> None:
    del key
    status = readiness()
    if not status["checkpoint"]:
        shutil.rmtree(models_root(), ignore_errors=True)
    runtime_staging = runtime_dir().with_name(".qwen3-tts-python.staging")
    shutil.rmtree(runtime_staging, ignore_errors=True)
    if not status["runtime"]:
        shutil.rmtree(runtime_dir(), ignore_errors=True)


def install_model() -> None:
    if not cuda_compatible():
        raise RuntimeError("Qwen3-TTS requires an NVIDIA CUDA GPU. Model files were not installed.")
    from backend.tools.shared.download_registry import DownloadCancelled, ModelDownloadRegistry

    registry = ModelDownloadRegistry.instance()
    registry.begin(KIND_QWEN_TTS, "customvoice")
    try:
        registry.check_cancelled()
        _download_checkpoint()
        registry.check_cancelled()
        _install_runtime()
        registry.check_cancelled()
    except DownloadCancelled:
        discard_partial()
        registry.fail(KIND_QWEN_TTS, "customvoice", keep_pending=True)
        raise
    except Exception:
        discard_partial()
        registry.fail(KIND_QWEN_TTS, "customvoice", keep_pending=False)
        raise
    registry.complete(KIND_QWEN_TTS, "customvoice")


def uninstall_model() -> None:
    shutil.rmtree(models_root(), ignore_errors=True)
    shutil.rmtree(runtime_dir(), ignore_errors=True)
